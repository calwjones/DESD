from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .models import Delivery


def _is_logistics(user):
    return user.is_authenticated and (user.role == 'logistics' or user.is_superuser)


@login_required
def logistics_dashboard(request):
    if not _is_logistics(request.user):
        messages.error(request, "Logistics access only.")
        return redirect('marketplace')

    deliveries = (
        Delivery.objects
        .exclude(status='delivered')
        .select_related('order', 'producer')
        .order_by('order__delivery_date')
    )
    return render(request, 'deliveries/dashboard.html', {
        'deliveries': deliveries,
    })


@login_required
@require_POST
def update_delivery_status(request, delivery_id):
    if not _is_logistics(request.user):
        messages.error(request, "Logistics access only.")
        return redirect('marketplace')

    delivery = get_object_or_404(Delivery, id=delivery_id)
    new_status = request.POST.get('status')

    try:
        delivery.transition_to(new_status)
        messages.success(
            request,
            f"Delivery #{delivery.id} for Order #{delivery.order.id} → "
            f"{delivery.get_status_display()}"
        )
    except ValueError as e:
        messages.error(request, str(e))

    return redirect('delivery:logistics_dashboard')