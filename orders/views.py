from django.shortcuts import redirect, render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from .cart import Cart
from .forms import CheckoutForm
from .models import Order, OrderItem
from products.models import Product
from services.os_places_service import PostcodesService
 
 
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
 
            # Save order
            full_address = f"{form.cleaned_data['delivery_address']}, {location['town']}, {postcode}"
            order = Order.objects.create(
                customer=request.user,
                total=total,
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
            cart.clear()
            return redirect("order_confirmation", order_id=order.id)
 
    else:
        form = CheckoutForm()
 
    return render(request, "orders/checkout.html", {
        "form": form,
        "cart_items": cart_items,
        "total": total,
    })
 
 
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