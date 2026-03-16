from .cart import Cart

def cart_count(request):
    cart = Cart(request)
    return {'cart_count': sum(cart.cart.values())}

