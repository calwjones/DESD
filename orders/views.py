from django.shortcuts import redirect
from django.shortcuts import render
from .cart import Cart


def add_to_cart(request, product_id):

    cart = Cart(request)

    cart.add(product_id)

    return redirect("view_cart")


def view_cart(request):

    cart = Cart(request)

    return render(request, "orders/cart.html", {"cart": cart})