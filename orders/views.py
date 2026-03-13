from django.shortcuts import redirect, render, get_object_or_404
from .cart import Cart
from products.models import Product


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
    return redirect("view_cart")


def view_cart(request):
    cart = Cart(request)

    cart_items = []
    producer_subtotals = {}
    total = 0

    for product_id, quantity in cart.cart.items():
        product = get_object_or_404(Product, id=product_id)
        subtotal = product.price * quantity
        total += subtotal

        # Track subtotals per producer
        producer_name = product.producer.username
        if producer_name not in producer_subtotals:
            producer_subtotals[producer_name] = 0
        producer_subtotals[producer_name] += subtotal

        cart_items.append({
            "product": product,
            "quantity": quantity,
            "subtotal": subtotal,
        })

    return render(
        request,
        "orders/cart.html",
        {
            "cart_items": cart_items,
            "total": total,
            "producer_subtotals": producer_subtotals,
        },
    )
