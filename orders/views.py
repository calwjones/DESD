from django.shortcuts import redirect
from .cart import Cart


def add_to_cart(request, product_id):

    cart = Cart(request)

    cart.add(product_id)

    return redirect("view_cart")