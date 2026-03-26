import random
import string
import stripe
from django.conf import settings
from django.contrib import messages
from django.core.mail import send_mail
from django.shortcuts import redirect, render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.urls import reverse
from .cart import Cart
from .forms import CheckoutForm
from .models import Order, OrderItem
from products.models import Product
from services.os_places_service import PostcodesService

stripe.api_key = settings.STRIPE_SECRET_KEY


def add_to_cart(request, product_id):
    cart = Cart(request)
    quantity = 1
    if request.method == "POST":
        try:
            quantity = max(1, int(request.POST.get("quantity", 1)))
        except ValueError:
            quantity = 1
    cart.add(product_id, quantity)
    next_url = request.POST.get("next") or request.META.get("HTTP_REFERER") or "view_cart"
    return redirect(next_url)


def remove_from_cart(request, product_id):
    cart = Cart(request)
    cart.remove(product_id)
    return redirect("view_cart")


def update_cart(request, product_id):
    if request.method == "POST":
        quantity = int(request.POST.get("quantity", 1))
        cart = Cart(request)
        cart.update(product_id, quantity)

        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            product = get_object_or_404(Product, id=product_id)
            item_subtotal = float(product.price * quantity)

            producer_subtotals = {}
            total = 0
            for pid, qty in cart.cart.items():
                p = get_object_or_404(Product, id=pid)
                subtotal = float(p.price * qty)
                total += subtotal
                producer_name = p.producer.username
                producer_subtotals[producer_name] = float(
                    producer_subtotals.get(producer_name, 0) + subtotal
                )

            return JsonResponse({
                "item_subtotal": f"{item_subtotal:.2f}",
                "producer_subtotals": {k: f"{v:.2f}" for k, v in producer_subtotals.items()},
                "total": f"{total:.2f}",
                'cart_count': sum(cart.cart.values()),
            })

    return redirect("view_cart")


@login_required
def checkout(request):
    cart = Cart(request)

    if not cart.cart:
        return redirect("view_cart")

    # Build cart items, group by producer, calculate food miles
    cart_items = []
    total = 0
    for product_id, quantity in cart.cart.items():
        product = get_object_or_404(
            Product.objects.select_related('producer__producer_profile'), id=product_id
        )
        subtotal = product.price * quantity
        total += subtotal
        cart_items.append({
            "product": product,
            "quantity": quantity,
            "subtotal": subtotal,
        })

    # Group items by producer and attach food miles per producer
    producers_data = {}
    for item in cart_items:
        username = item["product"].producer.username
        if username not in producers_data:
            producer_profile = getattr(item["product"].producer, "producer_profile", None)
            food_miles = None
            if request.user.latitude and producer_profile and producer_profile.latitude:
                food_miles = PostcodesService.calculate_food_miles(
                    request.user.latitude, request.user.longitude,
                    producer_profile.latitude, producer_profile.longitude,
                )
            producers_data[username] = {
                "name": getattr(producer_profile, "business_name", username),
                "items": [],
                "subtotal": 0,
                "food_miles": food_miles,
            }
        producers_data[username]["items"].append(item)
        producers_data[username]["subtotal"] += item["subtotal"]

    if request.method == "POST":
        form = CheckoutForm(request.POST)
        if form.is_valid():
            postcode = form.cleaned_data["postcode"]

            # Verify postcode via postcodes.io and get lat/lng for food miles
            service = PostcodesService()
            location = service.lookup_postcode(postcode)

            if location == PostcodesService.NETWORK_ERROR:
                form.add_error("postcode", "Could not reach the postcode service — please try again later.")
                return render(request, "orders/checkout.html", {
                    "form": form,
                    "producers_data": producers_data,
                    "total": total,
                })
            elif not location:
                form.add_error("postcode", "Invalid postcode — please check and try again.")
                return render(request, "orders/checkout.html", {
                    "form": form,
                    "producers_data": producers_data,
                    "total": total,
                })

            # Save order as pending
            full_address = f"{form.cleaned_data['delivery_address']}, {location['town']}, {postcode}"
            order = Order.objects.create(
                customer=request.user,
                total=total,
                status="pending",
                delivery_date=form.cleaned_data["delivery_date"],
                delivery_address=full_address,
            )
            for item in cart_items:
                OrderItem.objects.create(
                    order=order,
                    product=item["product"],
                    quantity=item["quantity"],
                    price=item["product"].price,
                )

            # Build Stripe line items
            line_items = []
            for item in cart_items:
                line_items.append({
                    "price_data": {
                        "currency": "gbp",
                        "unit_amount": int(item["product"].price * 100),  # pence
                        "product_data": {
                            "name": item["product"].name,
                        },
                    },
                    "quantity": item["quantity"],
                })

            # Create Stripe Checkout Session
            session = stripe.checkout.Session.create(
                payment_method_types=["card"],
                line_items=line_items,
                mode="payment",
                success_url=request.build_absolute_uri(
                    reverse("payment_success")
                ) + "?session_id={CHECKOUT_SESSION_ID}",
                cancel_url=request.build_absolute_uri(
                    reverse("payment_cancel") + f"?order_id={order.id}"
                ),
                metadata={"order_id": order.id},
            )

            # Store stripe session ID on order
            order.stripe_session_id = session.id
            order.save()

            cart.clear()

            return redirect(session.url)

    else:
        initial = {}
        if request.user.postcode:
            initial['postcode'] = request.user.postcode
        form = CheckoutForm(initial=initial)

    return render(request, "orders/checkout.html", {
        "form": form,
        "producers_data": producers_data,
        "total": total,
    })


@login_required
def payment_success(request):
    session_id = request.GET.get("session_id")
    if not session_id:
        return redirect("marketplace")

    order = get_object_or_404(
        Order,
        stripe_session_id=session_id,
        customer=request.user,
    )

    # Verify payment with Stripe
    session = stripe.checkout.Session.retrieve(session_id)
    if session.payment_status == "paid" and order.status != "confirmed":
        order.status = "confirmed"
        order.save()
        _send_confirmation_emails(order)

    return render(request, "orders/order_confirmation.html", {"order": order})


@login_required
def payment_cancel(request):
    order_id = request.GET.get("order_id")
    if order_id:
        # Mark order as cancelled since they abandoned payment
        try:
            order = Order.objects.get(id=order_id, customer=request.user)
            order.status = "cancelled"
            order.save()
        except Order.DoesNotExist:
            pass
    return render(request, "orders/payment_cancelled.html")


@csrf_exempt
def stripe_webhook(request):
    payload = request.body
    sig_header = request.META.get("HTTP_STRIPE_SIGNATURE")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except (ValueError, stripe.error.SignatureVerificationError):
        return HttpResponse(status=400)

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        order_id = session.get("metadata", {}).get("order_id")
        if order_id:
            try:
                order = Order.objects.get(id=order_id)
                order.status = "confirmed"
                order.save()
            except Order.DoesNotExist:
                pass

    return HttpResponse(status=200)


@login_required
def order_confirmation(request, order_id):
    order = get_object_or_404(Order, id=order_id, customer=request.user)
    return render(request, "orders/order_confirmation.html", {"order": order})


@login_required
def order_history(request):
    if request.user.role != 'customer':
        return redirect('producer_dashboard')
    orders = Order.objects.filter(customer=request.user).prefetch_related('items__product').order_by('-created_at')
    return render(request, "orders/order_history.html", {"orders": orders})


@login_required
def toggle_item_packed(request, item_id):
    if request.method != "POST" or request.user.role != 'producer':
        return redirect('producer_dashboard')
    item = get_object_or_404(OrderItem, id=item_id, product__producer=request.user)
    item.is_packed = not item.is_packed
    item.save()
    return redirect('producer_dashboard')


@login_required
def pack_all_items(request, order_id):
    if request.method != "POST" or request.user.role != 'producer':
        return redirect('producer_dashboard')
    order = get_object_or_404(Order, id=order_id)
    OrderItem.objects.filter(order=order, product__producer=request.user).update(is_packed=True)
    return redirect('producer_dashboard')


@login_required
def mark_order_ready(request, order_id):
    if request.method != "POST" or request.user.role != 'producer':
        return redirect('producer_dashboard')
    order = get_object_or_404(Order, id=order_id)
    if not OrderItem.objects.filter(order=order, product__producer=request.user).exists():
        return redirect('producer_dashboard')
    order.status = "processing"
    order.save()
    messages.success(request, f"Order #{order.id} marked as ready for dispatch.")
    return redirect('producer_dashboard')


@login_required
def ship_order(request, order_id):
    if request.method != "POST" or request.user.role != 'producer':
        return redirect('producer_dashboard')
    order = get_object_or_404(Order, id=order_id)
    if not OrderItem.objects.filter(order=order, product__producer=request.user).exists():
        return redirect('producer_dashboard')
    tracking = "DESD-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=10))
    order.status = "dispatched"
    order.tracking_number = tracking
    order.save()
    _send_dispatch_email(order)
    messages.success(request, f"Order #{order.id} shipped. Tracking: {tracking}")
    return redirect('producer_dashboard')


def _send_confirmation_emails(order):
    items = order.items.select_related('product__producer__producer_profile').all()

    # Email to customer
    item_lines = "\n".join(
        f"  - {i.product.name} x{i.quantity} @ £{i.price} = £{i.subtotal()}"
        for i in items
    )
    send_mail(
        subject=f"Order #{order.id} Confirmed — DESD Marketplace",
        message=(
            f"Hi {order.customer.username},\n\n"
            f"Your order has been confirmed!\n\n"
            f"Order #{order.id}\n"
            f"Delivery date: {order.delivery_date}\n"
            f"Delivery address: {order.delivery_address}\n\n"
            f"Items:\n{item_lines}\n\n"
            f"Total: £{order.total}\n\n"
            f"Thanks for shopping with DESD Marketplace."
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[order.customer.email],
        fail_silently=True,
    )

    # Email to each producer with only their items
    producer_items = {}
    for item in items:
        producer = item.product.producer
        producer_items.setdefault(producer, []).append(item)

    for producer, prod_items in producer_items.items():
        prod_item_lines = "\n".join(
            f"  - {i.product.name} x{i.quantity}"
            for i in prod_items
        )
        profile = getattr(producer, 'producer_profile', None)
        recipient = (profile.contact_email if profile and profile.contact_email else producer.email)
        send_mail(
            subject=f"New Order #{order.id} — DESD Marketplace",
            message=(
                f"Hi {getattr(profile, 'business_name', producer.username)},\n\n"
                f"You have a new order to fulfil.\n\n"
                f"Order #{order.id}\n"
                f"Customer: {order.customer.username}\n"
                f"Delivery date: {order.delivery_date}\n"
                f"Delivery address: {order.delivery_address}\n\n"
                f"Your items to prepare:\n{prod_item_lines}\n\n"
                f"Log in to your dashboard to manage this order."
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient],
            fail_silently=True,
        )


def _send_dispatch_email(order):
    send_mail(
        subject=f"Order #{order.id} Dispatched — DESD Marketplace",
        message=(
            f"Hi {order.customer.username},\n\n"
            f"Great news — your order has been dispatched!\n\n"
            f"Order #{order.id}\n"
            f"Tracking number: {order.tracking_number}\n"
            f"Expected delivery: {order.delivery_date}\n"
            f"Delivery address: {order.delivery_address}\n\n"
            f"Thanks for shopping with DESD Marketplace."
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[order.customer.email],
        fail_silently=True,
    )


@login_required
def view_cart(request):
    cart = Cart(request)
    cart_items = []
    producer_subtotals = {}
    total = 0
    for product_id, quantity in cart.cart.items():
        product = get_object_or_404(Product, id=product_id)
        subtotal = product.price * quantity
        total += subtotal
        producer_name = product.producer.username
        if producer_name not in producer_subtotals:
            producer_subtotals[producer_name] = 0
        producer_subtotals[producer_name] += subtotal
        cart_items.append({
            "product": product,
            "quantity": quantity,
            "subtotal": subtotal,
        })
    return render(request, "orders/cart.html", {
        "cart_items": cart_items,
        "total": total,
        "producer_subtotals": producer_subtotals,
    })
