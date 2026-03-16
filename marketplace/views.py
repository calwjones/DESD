from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from products.models import Product


@login_required
def marketplace_view(request):
    if request.user.role == 'producer':
        return redirect('producer_dashboard')
 
    products = Product.objects.filter(is_available=True).order_by('-created_at')
 
    query = request.GET.get('q', '').strip()
    category = request.GET.get('category', '').strip()
    organic_only = request.GET.get('organic') == 'on'
 
    if query:
        products = products.filter(name__icontains=query) | products.filter(description__icontains=query)
 
    if category:
        products = products.filter(category=category)
 
    if organic_only:
        products = products.filter(is_organic=True)
 
    categories = Product.CATEGORY_CHOICES
 
    return render(request, 'marketplace.html', {
        'products': products,
        'query': query,
        'selected_category': category,
        'organic_only': organic_only,
        'categories': categories,
    })


@login_required
def producer_dashboard_view(request):
    if request.user.role == 'customer':
        return redirect('marketplace')
    products = Product.objects.filter(producer=request.user).order_by('-created_at')
    return render(request, 'dashboard.html', {'products': products})
