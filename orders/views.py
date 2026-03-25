import stripe
from django.conf import settings
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
    cart.add(product_id)
    return redirect("view_cart")


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

    # Build cart items and total
    cart_items = []
    total = 0
    for product_id, quantity in cart.cart.items():
        product = get_object_or_404(Product, id=product_id)
        subtotal = product.price * quantity
        total += subtotal
        cart_items.append({
            "product": product,
            "quantity": quantity,
            "subtotal": subtotal,
        })

    if request.method == "POST":
        form = CheckoutForm(request.POST)
        if form.is_valid():
            postcode = form.cleaned_data["postcode"]

            # Verify postcode via postcodes.io and get lat/lng for food miles
            service = PostcodesService()
            location = service.lookup_postcode(postcode)

            if not location:
                form.add_error("postcode", "Invalid postcode — please check and try again.")
                return render(request, "orders/checkout.html", {
                    "form": form,
                    "cart_items": cart_items,
                    "total": total,
                })

            # Calculate food miles per producer
            food_miles = {}
            for item in cart_items:
                producer_profile = getattr(item["product"].producer, "producer_profile", None)
                if producer_profile and producer_profile.latitude:
                    miles = service.calculate_food_miles(
                        producer_profile.latitude,
                        producer_profile.longitude,
                        location["latitude"],
                        location["longitude"],
                    )
                    food_miles[item["product"].producer.username] = miles

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
        form = CheckoutForm()

    return render(request, "orders/checkout.html", {
        "form": form,
        "cart_items": cart_items,
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
    if session.payment_status == "paid":
        order.status = "confirmed"
        order.save()

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
