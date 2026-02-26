from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from products.models import Product


@login_required
def marketplace_view(request):
    if request.user.role == 'producer':
        return redirect('producer_dashboard')
    products = Product.objects.filter(is_available=True).order_by('-created_at')
    return render(request, 'marketplace.html', {'products': products})


@login_required
def producer_dashboard_view(request):
    if request.user.role == 'customer':
        return redirect('marketplace')
    products = Product.objects.filter(producer=request.user).order_by('-created_at')
    return render(request, 'dashboard.html', {'products': products})
