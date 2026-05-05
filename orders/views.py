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
from django.utils.http import url_has_allowed_host_and_scheme
from decimal import Decimal, ROUND_HALF_UP
from .cart import Cart
from .forms import CheckoutForm, RecurringOrderForm
from .models import Order, OrderItem, Payment, PaymentSplit, RecurringOrder, RecurringOrderItem
from .services import calculate_commission_split, COMMISSION_RATE
from products.models import Product
from services.os_places_service import PostcodesService
import requests
from django.utils import timezone
from delivery.models import Delivery

stripe.api_key = settings.STRIPE_SECRET_KEY
DEMAND_SERVICE_URL = getattr(settings, 'DEMAND_SERVICE_URL')

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
    if not url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        next_url = "view_cart"
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
        subtotal = product.current_price * quantity
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
            producers_data[username] = {
                "name": getattr(producer_profile, "business_name", username),
                "items": [],
                "subtotal": 0,
                "food_miles": PostcodesService.get_food_miles(request.user, item["product"].producer),
            }
        producers_data[username]["items"].append(item)
        producers_data[username]["subtotal"] += item["subtotal"]

    # 5% network commission shown for transparency (TC-007). Customer pays `total`;
    # the commission is deducted from the producer's payout.
    commission_amount = (Decimal(total) * COMMISSION_RATE).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

    if request.method == "POST":
        form = CheckoutForm(request.POST)
        if form.is_valid():
            postcode = form.cleaned_data["postcode"]
            service = PostcodesService()
            location = service.lookup_postcode(postcode)
            
            if location == PostcodesService.NETWORK_ERROR:
                # API down - accept the postcode without enrichment so checkout
                # isn't blocked by a third-party outage
                messages.warning(
                    request,
                    "Could not verify postcode against the postcode service. "
                    "Your order will be processed using the postcode as entered."
                )
                location = None
            elif not location:
                form.add_error("postcode", "Invalid postcode - please check and try again.")
                return render(request, "orders/checkout.html", {
                    "form": form,
                    "producers_data": producers_data,
                    "total": total,
                    "commission_amount": commission_amount,
                })
            
            # Validate stock before creating the order
            out_of_stock = [
                item for item in cart_items
                if item["product"].stock_quantity < item["quantity"]
            ]
            if out_of_stock:
                names = ", ".join(i["product"].name for i in out_of_stock)
                messages.error(request, f"Not enough stock for: {names}. Please update your basket.")
                return redirect("view_cart")
            
            # Build address with or without town
            if location:
                full_address = f"{form.cleaned_data['delivery_address']}, {location['town']}, {postcode}"
            else:
                full_address = f"{form.cleaned_data['delivery_address']}, {postcode}"
                
            order = Order.objects.create(
                customer=request.user,
                total=total,
                status="pending",
                delivery_date=form.cleaned_data["delivery_date"],
                delivery_address=full_address,
                delivery_instructions=form.cleaned_data.get("delivery_instructions", ""),
            )
            for item in cart_items:
                OrderItem.objects.create(
                    order=order,
                    product=item["product"],
                    quantity=item["quantity"],
                    price=item["product"].current_price,
                )

            # Build Stripe line items
            line_items = []
            for item in cart_items:
                line_items.append({
                    "price_data": {
                        "currency": "gbp",
                        "unit_amount": int(item["product"].current_price * 100),  # pence
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

            # Create pending Payment record + per-producer splits (BRFN-41)
            split = calculate_commission_split(order)
            payment = Payment.objects.create(
                order=order,
                stripe_session_id=session.id,
                amount=total,
                commission_amount=split["total_commission"],
                producer_net=split["total_net"],
                currency="GBP",
                status="pending",
            )
            for s in split["splits"]:
                PaymentSplit.objects.create(
                    payment=payment,
                    producer=s["producer"],
                    gross_amount=s["gross"],
                    commission_amount=s["commission"],
                    net_amount=s["net"],
                )

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
        "commission_amount": commission_amount,
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
        _record_successful_payment(order, session)
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
            Payment.objects.filter(order=order).update(status="failed")
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
                if order.status != "confirmed":
                    order.status = "confirmed"
                    order.save()
                _record_successful_payment(order, session)
            except Order.DoesNotExist:
                pass

    return HttpResponse(status=200)


@login_required
def order_confirmation(request, order_id):
    order = get_object_or_404(Order, id=order_id, customer=request.user)
    return render(request, "orders/order_confirmation.html", {"order": order})


@login_required
def order_history(request):
    if not request.user.is_buyer:
        return redirect('marketplace')

    orders_qs = Order.objects.filter(customer=request.user).prefetch_related(
        'items__product__producer__producer_profile',
        'deliveries__producer',
    ).order_by('-created_at')

    # Filters
    start_date = request.GET.get('start_date', '').strip()
    end_date = request.GET.get('end_date', '').strip()
    producer_id = request.GET.get('producer', '').strip()

    if start_date:
        orders_qs = orders_qs.filter(created_at__date__gte=start_date)
    if end_date:
        orders_qs = orders_qs.filter(created_at__date__lte=end_date)
    if producer_id:
        orders_qs = orders_qs.filter(items__product__producer_id=producer_id).distinct()

    orders = list(orders_qs)

    # Producer dropdown — distinct producers across all of this customer's orders
    from accounts.models import CustomUser
    producer_ids = OrderItem.objects.filter(
        order__customer=request.user
    ).values_list('product__producer_id', flat=True).distinct()
    producer_choices = (
        CustomUser.objects.filter(id__in=producer_ids)
        .select_related('producer_profile')
        .order_by('username')
    )

    # Group items by producer for each order (multi-vendor breakdown)
    for order in orders:
        groups = {}
        # Map producer_id -> Delivery for this order, single query
        deliveries_by_producer = {
            d.producer_id: d for d in order.deliveries.all()
        }
        for item in order.items.all():
            producer = item.product.producer
            key = producer.id
            if key not in groups:
                profile = getattr(producer, 'producer_profile', None)
                delivery = deliveries_by_producer.get(producer.id)
                groups[key] = {
                    'producer': producer,
                    'name': getattr(profile, 'business_name', producer.username),
                    'username': producer.username,
                    'items': [],
                    'subtotal': 0,
                    'delivery_status': delivery.status if delivery else None,
                    'delivery_status_display': delivery.get_status_display() if delivery else None,
                    'tracking_number': delivery.tracking_number if delivery else '',
                }
            groups[key]['items'].append(item)
            groups[key]['subtotal'] += item.subtotal()
        order.producer_groups = list(groups.values())

    # Fetch AI recommendations
    recommended_products = []
    try:
        resp = requests.post(
            f"{DEMAND_SERVICE_URL}/predict",
            json={"customer_id": request.user.id, "top_n": 5},
            timeout=5,
        )
        if resp.status_code == 200:
            recommendations = resp.json().get("recommendations", [])
            # Try to match recommended product names to marketplace products
            product_names = [r["product_name"] for r in recommendations if r.get("product_name")]
            matched = Product.objects.filter(
                name__in=product_names,
                is_available=True
            )
            recommended_products = list(matched)
    except requests.RequestException:
        pass

    return render(request, "orders/order_history.html", {
        "orders": orders,
        "recommended_products": recommended_products,
        "start_date": start_date,
        "end_date": end_date,
        "selected_producer": producer_id,
        "producer_choices": producer_choices,
        "filters_active": bool(start_date or end_date or producer_id),
    })


@login_required
def reorder(request, order_id):
    if request.method != 'POST' or not request.user.is_buyer:
        return redirect('order_history')

    order = get_object_or_404(Order, id=order_id, customer=request.user)
    cart = Cart(request)

    added = []        # list of (name, qty)
    flagged = []      # list of (name, reason)

    for item in order.items.select_related('product').all():
        product = item.product
        if not product.is_available:
            flagged.append((product.name, "no longer available"))
            continue
        if product.stock_quantity == 0:
            flagged.append((product.name, "out of stock"))
            continue
        qty = min(item.quantity, product.stock_quantity)
        cart.add(product.id, qty)
        added.append((product.name, qty))
        if qty < item.quantity:
            flagged.append((product.name, f"only {qty} available (you originally ordered {item.quantity})"))

    if added:
        added_names = ", ".join(f"{name} ×{qty}" for name, qty in added)
        messages.success(request, f"Added to cart: {added_names}")
    if flagged:
        flagged_names = "; ".join(f"{name} — {reason}" for name, reason in flagged)
        messages.warning(request, f"Some items couldn't be added: {flagged_names}")
    if not added and not flagged:
        messages.info(request, "Nothing to reorder.")

    return redirect('view_cart')


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
    if not order.items.filter(product__producer=request.user).exists():
        return redirect('producer_dashboard')
    # Only change status if this producer's items are all packed
    all_packed = not order.items.filter(is_packed=False, product__producer=request.user).exists()
    if not all_packed:
        messages.warning(request, f"Order #{order.id} still has unpacked items. Please pack all your items first.")
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

    # Verify this producer has items in this order
    if not order.items.filter(product__producer=request.user).exists():
        messages.error(request, "You don't have items in this order.")
        return redirect('producer_dashboard')
    delivery = get_object_or_404(Delivery, order=order, producer=request.user)
    
    # Producer must have packed all their items
    unpacked = order.items.filter(
        product__producer=request.user,
        is_packed=False,
    ).exists()
    if unpacked:
        messages.warning(request, "Pack all your items before marking ready for collection.")
        return redirect('producer_dashboard')
    
    # Don't double-mark
    if delivery.producer_ready_at:
        messages.info(request, "Already marked ready for collection.")
        return redirect('producer_dashboard')
    
    # Mark this producer's delivery as ready
    delivery.producer_ready_at = timezone.now()
    delivery.tracking_number = "DESD-" + "".join(
        random.choices(string.ascii_uppercase + string.digits, k=10)
    )
    delivery.save()
    
    _send_dispatch_email(delivery)
    messages.success(
        request,
        f"Marked ready for collection. Tracking: {delivery.tracking_number}"
    )
    return redirect('producer_dashboard')


def _record_successful_payment(order, session):
    payment_intent_id = session.payment_intent or ""
    session_id = session.id or order.stripe_session_id
    payment, _ = Payment.objects.get_or_create(
        order=order,
        defaults={
            "amount": order.total,
            "currency": "GBP",
            "stripe_session_id": session_id,
        },
    )
    payment.stripe_session_id = session_id
    payment.stripe_payment_intent_id = payment_intent_id
    payment.status = "succeeded"
    payment.save()


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

def _send_out_for_delivery_email(delivery):
    """Email the customer when *one* of their producers' deliveries is out
    on the van. Per-delivery (not per-order) so multi-vendor orders get one
    email per delivery."""
    order = delivery.order
    send_mail(
        subject=f"Order #{order.id} Out for Delivery — DESD Marketplace",
        message=(
            f"Hi {order.customer.username},\n\n"
            f"Your order from {delivery.producer.username} is out for delivery "
            f"and on its way to you.\n\n"
            f"Order #{order.id}\n"
            f"Tracking number: {delivery.tracking_number}\n"
            f"Delivery address: {order.delivery_address}\n\n"
            f"Thanks for shopping with DESD Marketplace."
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[order.customer.email],
        fail_silently=True,
    )


def _send_delivered_email(order):
    send_mail(
        subject=f"Order #{order.id} Delivered — DESD Marketplace",
        message=(
            f"Hi {order.customer.username},\n\n"
            f"Your order has been delivered. We hope you enjoy it!\n\n"
            f"Order #{order.id}\n"
            f"Delivery address: {order.delivery_address}\n\n"
            f"Thanks for shopping with DESD Marketplace."
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[order.customer.email],
        fail_silently=True,
    )


def _send_dispatch_email(delivery):
    order = delivery.order
    send_mail(
        subject=f"Order #{order.id} Dispatched — DESD Marketplace",
        message=(
            f"Hi {order.customer.username},\n\n"
            f"Great news — your order from {delivery.producer.username} has been dispatched!\n\n"
            f"Order #{order.id}\n"
            f"Tracking number: {delivery.tracking_number}\n"
            f"Expected delivery: {order.delivery_date}\n"
            f"Delivery address: {order.delivery_address}\n\n"
            f"Thanks for shopping with DESD Marketplace."
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[order.customer.email],
        fail_silently=True,
    )


@login_required
def recurring_orders_list(request):
    """TC-018: list this customer's recurring order templates."""
    if not request.user.is_buyer:
        return redirect('marketplace')
    templates = (
        RecurringOrder.objects
        .filter(customer=request.user)
        .prefetch_related('items__product__producer')
    )
    return render(request, 'orders/recurring_orders_list.html', {
        'templates': templates,
    })


@login_required
def save_cart_as_recurring(request):
    """TC-018: turn the current session cart into a recurring template."""
    if not request.user.is_buyer:
        return redirect('marketplace')

    cart = Cart(request)
    if not cart.cart:
        messages.error(request, 'Your cart is empty — add items before saving as a recurring order.')
        return redirect('view_cart')

    # Build cart preview for the template
    cart_items = []
    for product_id, quantity in cart.cart.items():
        product = get_object_or_404(Product, id=product_id)
        cart_items.append({
            'product': product,
            'quantity': quantity,
            'subtotal': product.current_price * quantity,
        })

    if request.method == 'POST':
        form = RecurringOrderForm(request.POST)
        if form.is_valid():
            ro = form.save(commit=False)
            ro.customer = request.user
            ro.save()
            for ci in cart_items:
                RecurringOrderItem.objects.create(
                    recurring_order=ro,
                    product=ci['product'],
                    quantity=ci['quantity'],
                )
            messages.success(
                request,
                f"Saved as recurring order. Will auto-generate every "
                f"{ro.get_recurrence_day_display()} for {ro.get_delivery_day_display()} delivery."
            )
            return redirect('recurring_orders_list')
    else:
        # Pre-fill delivery address from a recent order if available
        last_order = (
            Order.objects.filter(customer=request.user)
            .exclude(delivery_address='')
            .order_by('-created_at')
            .first()
        )
        initial = {}
        if last_order:
            initial['delivery_address'] = last_order.delivery_address
        form = RecurringOrderForm(initial=initial)

    return render(request, 'orders/save_cart_as_recurring.html', {
        'form': form,
        'cart_items': cart_items,
    })


@login_required
def recurring_order_detail(request, pk):
    if not request.user.is_buyer:
        return redirect('marketplace')
    ro = get_object_or_404(
        RecurringOrder.objects.prefetch_related('items__product__producer'),
        pk=pk,
        customer=request.user,
    )
    return render(request, 'orders/recurring_order_detail.html', {
        'recurring_order': ro,
    })


@login_required
def recurring_order_toggle(request, pk):
    """Pause or resume a recurring order."""
    if request.method != 'POST' or not request.user.is_buyer:
        return redirect('recurring_orders_list')
    ro = get_object_or_404(RecurringOrder, pk=pk, customer=request.user)
    ro.is_active = not ro.is_active
    ro.save()
    state = 'resumed' if ro.is_active else 'paused'
    messages.success(request, f"Recurring order {state}.")
    return redirect('recurring_orders_list')


@login_required
def recurring_order_delete(request, pk):
    if request.method != 'POST' or not request.user.is_buyer:
        return redirect('recurring_orders_list')
    ro = get_object_or_404(RecurringOrder, pk=pk, customer=request.user)
    ro.delete()
    messages.success(request, "Recurring order deleted.")
    return redirect('recurring_orders_list')


@login_required
def view_cart(request):
    cart = Cart(request)
    cart_items = []
    producers_info = {}  # {username: {subtotal, food_miles}}
    total = 0
    for product_id, quantity in cart.cart.items():
        product = get_object_or_404(
            Product.objects.select_related('producer__producer_profile'), id=product_id
        )
        subtotal = product.price * quantity
        total += subtotal
        producer_name = product.producer.username
        if producer_name not in producers_info:
            producers_info[producer_name] = {
                "subtotal": 0,
                "food_miles": PostcodesService.get_food_miles(request.user, product.producer),
            }
        producers_info[producer_name]["subtotal"] += subtotal
        cart_items.append({
            "product": product,
            "quantity": quantity,
            "subtotal": subtotal,
        })

    miles_values = [p["food_miles"] for p in producers_info.values() if p["food_miles"] is not None]
    total_food_miles = round(sum(miles_values), 1) if miles_values else None

    return render(request, "orders/cart.html", {
        "cart_items": cart_items,
        "total": total,
        "producers_info": producers_info,
        "total_food_miles": total_food_miles,
    })
