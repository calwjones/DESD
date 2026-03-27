from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from orders.models import Order, OrderItem
from products.models import Product
from services.os_places_service import PostcodesService


@login_required
def marketplace_view(request):
    products = Product.objects.filter(is_available=True).select_related(
        'producer__producer_profile'
    ).order_by('-created_at')

    query = request.GET.get('q', '').strip()
    category = request.GET.get('category', '').strip()
    organic_only = request.GET.get('organic') == 'on'

    if query:
        products = products.filter(name__icontains=query) | products.filter(description__icontains=query)

    if category:
        products = products.filter(category=category)

    if organic_only:
        products = products.filter(is_organic=True)

    # Attach food_miles to each product if customer has a saved postcode
    products = list(products)
    for product in products:
        product.food_miles = PostcodesService.get_food_miles(request.user, product.producer)

    categories = Product.CATEGORY_CHOICES

    return render(request, 'marketplace.html', {
        'products': products,
        'query': query,
        'selected_category': category,
        'organic_only': organic_only,
        'categories': categories,
        'customer_has_postcode': bool(request.user.postcode),
    })


@login_required
def producer_dashboard_view(request):
    if request.user.role == 'customer':
        return redirect('marketplace')
    products = Product.objects.filter(producer=request.user).order_by('-created_at')

    # Orders containing this producer's items, excluding terminal states
    active_statuses = ['confirmed', 'processing']
    order_ids = OrderItem.objects.filter(
        product__producer=request.user,
        order__status__in=active_statuses,
    ).values_list('order_id', flat=True).distinct()
    orders = (
        Order.objects.filter(id__in=order_ids)
        .prefetch_related('items__product')
        .select_related('customer')
        .order_by('delivery_date')
    )
    # Attach only this producer's items to each order for template use
    for order in orders:
        order.producer_items = [
            item for item in order.items.all()
            if item.product.producer_id == request.user.id
        ]

    # Sprint 3: AI service will provide demand forecasts
    demand_forecasts = []

    return render(request, 'dashboard.html', {
        'products': products,
        'orders': orders,
        'demand_forecasts': demand_forecasts,
    })
