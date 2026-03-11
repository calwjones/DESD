from django.shortcuts import redirect
from django.shortcuts import render
from .cart import Cart
from products.models import Product


def add_to_cart(request, product_id):

    cart = Cart(request)

    cart.add(product_id)

    return redirect("view_cart")




def view_cart(request):

    cart = Cart(request)

    cart_items = []
    total = 0

    for product_id, quantity in cart.cart.items():

        product = Product.objects.get(id=product_id)
        
        subtotal = product.price * quantity

        total += subtotal


        cart_items.append({
            "product": product,
            "quantity": quantity,
            "subtotal": subtotal
        })

      
    return render(
        request,
        "orders/cart.html",
        {
            "cart_items": cart_items,
            "total": total
        }
    )