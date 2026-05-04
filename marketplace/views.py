from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import redirect, render
from django.utils import timezone

from accounts.models import FavouriteProducer
from orders.models import Order, OrderItem
from products.models import Product
from services.os_places_service import PostcodesService
import requests
from django.conf import settings

DEMAND_SERVICE_URL = getattr(settings, 'DEMAND_SERVICE_URL')

@login_required
def marketplace_view(request):
    today = timezone.now().date()
    products = Product.objects.filter(
        is_available=True,
    ).filter(
        Q(best_before_date__isnull=True) | Q(best_before_date__gte=today)
    ).select_related(
        'producer__producer_profile'
    ).order_by('-created_at')

    query = request.GET.get('q', '').strip()
    category = request.GET.get('category', '').strip()
    organic_only = request.GET.get('organic') == 'on'
    surplus_only = request.GET.get('surplus') == 'on'
    hide_allergens = request.GET.get('hide_allergens') == 'on'

    if query:
        products = products.filter(name__icontains=query) | products.filter(description__icontains=query) | products.filter(producer__producer_profile__business_name__icontains=query) | products.filter(producer__username__icontains=query)

    if category:
        products = products.filter(category=category)

    if organic_only:
        products = products.filter(is_organic=True)

    if surplus_only:
        now = timezone.now()
        products = products.filter(is_surplus=True).filter(
            Q(surplus_expires_at__isnull=True) | Q(surplus_expires_at__gt=now)
        )

    # Attach food_miles to each product if customer has a saved postcode
    products = list(products)
    for product in products:
        product.food_miles = PostcodesService.get_food_miles(request.user, product.producer)

    # Filter out products containing any of the customer's avoided allergens
    if hide_allergens and request.user.role == 'customer' and request.user.avoided_allergens:
        avoided = set(a.strip() for a in request.user.avoided_allergens.split(',') if a.strip())
        products = [
            p for p in products
            if not set(a.strip() for a in p.allergen_info.split(',') if a.strip()).intersection(avoided)
        ]

    categories = Product.CATEGORY_CHOICES

    favourite_producer_ids = set()
    if request.user.role == 'customer':
        favourite_producer_ids = set(
            FavouriteProducer.objects.filter(customer=request.user).values_list('producer_id', flat=True)
        )

    return render(request, 'marketplace.html', {
        'products': products,
        'query': query,
        'selected_category': category,
        'organic_only': organic_only,
        'surplus_only': surplus_only,
        'hide_allergens': hide_allergens,
        'categories': categories,
        'customer_has_postcode': bool(request.user.postcode),
        'favourite_producer_ids': favourite_producer_ids,
        'user_has_allergens': bool(request.user.role == 'customer' and request.user.avoided_allergens),
    })


@login_required
def producer_dashboard_view(request):
    if request.user.role == 'customer':
        return redirect('marketplace')
    products = Product.objects.filter(producer=request.user).order_by('-created_at')
    low_stock_products = [p for p in products if p.is_low_stock]
    active_statuses = ['confirmed', 'processing', 'dispatched', 'partially_delivered']
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

    for order in orders:
        order.producer_items = [
            item for item in order.items.all()
            if item.product.producer_id == request.user.id
        ]
        order.my_delivery = order.deliveries.filter(producer=request.user).first()
        order.all_my_items_packed = bool(order.producer_items) and all(
            item.is_packed for item in order.producer_items
        )

    # Fetch demand forecasts from AI service
    demand_forecasts = []
    try:
        resp = requests.get(f"{DEMAND_SERVICE_URL}/forecast", timeout=5)
        if resp.status_code == 200:
            demand_forecasts = resp.json()
    except requests.RequestException:
        pass  # Fail silently, template handles empty list

    return render(request, 'dashboard.html', {
        'products': products,
        'orders': orders,
        'demand_forecasts': demand_forecasts,
        'low_stock_products': low_stock_products,  # new
    })
