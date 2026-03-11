class Cart:

    def __init__(self, request):
        self.session = request.session
        cart = self.session.get("cart")

        if not cart:
            cart = self.session["cart"] = {}

        self.cart = cart


    def add(self, product_id, quantity=1):

        product_id = str(product_id)

        if product_id not in self.cart:
            self.cart[product_id] = 0

        self.cart[product_id] += quantity

        self.save()


    def remove(self, product_id):

        product_id = str(product_id)

        if product_id in self.cart:
            del self.cart[product_id]

        self.save()


    def save(self):
        self.session.modified = True