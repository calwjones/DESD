from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render


@login_required
def marketplace_view(request):
    if request.user.role == 'producer':
        return redirect('producer_dashboard')
    return render(request, 'marketplace.html')


@login_required
def producer_dashboard_view(request):
    if request.user.role == 'customer':
        return redirect('marketplace')
    return render(request, 'dashboard.html')
