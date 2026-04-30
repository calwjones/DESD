import csv
from datetime import date
from decimal import Decimal
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from .forms import ProducerProfileForm
from .models import ProducerProfile
from orders.models import Settlement
from services.os_places_service import PostcodesService


@login_required
def edit_profile(request):
    if request.user.role != 'producer':
        return redirect('marketplace')

    profile, _ = ProducerProfile.objects.get_or_create(user=request.user)

    if request.method == 'POST':
        form = ProducerProfileForm(request.POST, instance=profile)
        if form.is_valid():
            updated_profile = form.save(commit=False)
            if updated_profile.postcode:
                location = PostcodesService().lookup_postcode(updated_profile.postcode)
                if location == PostcodesService.NETWORK_ERROR:
                    form.add_error('postcode', 'Could not reach the postcode service — please try again later.')
                    return render(request, 'producers/profile_edit.html', {'form': form})
                elif not location:
                    form.add_error('postcode', 'Invalid postcode — please check and try again.')
                    return render(request, 'producers/profile_edit.html', {'form': form})
                else:
                    updated_profile.latitude = location['latitude']
                    updated_profile.longitude = location['longitude']
            updated_profile.save()
            messages.success(request, 'Profile updated.')
            return redirect('producer_dashboard')
    else:
        form = ProducerProfileForm(instance=profile)

    return render(request, 'producers/profile_edit.html', {'form': form})


def _producer_only(request):
    """Return None if the user is a producer, else a redirect."""
    if request.user.role != 'producer':
        return redirect('marketplace')
    return None


@login_required
def settlements_list(request):
    """BRFN-44: Producer's weekly payment history with running YTD total."""
    redirect_response = _producer_only(request)
    if redirect_response:
        return redirect_response

    settlements = Settlement.objects.filter(producer=request.user)

    today = date.today()
    ytd = (
        Settlement.objects
        .filter(producer=request.user, period_end__year=today.year)
        .aggregate(
            gross=Sum('gross_amount'),
            commission=Sum('commission_amount'),
            net=Sum('net_amount'),
        )
    )
    ytd_totals = {
        'year': today.year,
        'gross': ytd['gross'] or Decimal('0'),
        'commission': ytd['commission'] or Decimal('0'),
        'net': ytd['net'] or Decimal('0'),
    }

    return render(request, 'producers/settlements_list.html', {
        'settlements': settlements,
        'ytd': ytd_totals,
    })


@login_required
def settlement_detail(request, settlement_id):
    """Show contributing orders for a single settlement."""
    redirect_response = _producer_only(request)
    if redirect_response:
        return redirect_response

    settlement = get_object_or_404(
        Settlement, id=settlement_id, producer=request.user
    )
    splits = (
        settlement.splits
        .select_related('payment__order__customer', 'payment')
        .order_by('payment__created_at')
    )

    return render(request, 'producers/settlement_detail.html', {
        'settlement': settlement,
        'splits': splits,
    })


@login_required
def settlement_csv(request, settlement_id):
    """Download a CSV breakdown of a settlement for tax records (TC-012)."""
    redirect_response = _producer_only(request)
    if redirect_response:
        return redirect_response

    settlement = get_object_or_404(
        Settlement, id=settlement_id, producer=request.user
    )

    response = HttpResponse(content_type='text/csv')
    filename = f"settlement_{settlement.period_start}_{settlement.period_end}.csv"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    writer = csv.writer(response)
    writer.writerow([
        'Order #', 'Order Date', 'Customer', 'Gross (£)', 'Commission (£)', 'Net (£)',
    ])
    splits = settlement.splits.select_related('payment__order__customer', 'payment')
    for split in splits:
        order = split.payment.order
        writer.writerow([
            order.id,
            split.payment.created_at.date().isoformat(),
            order.customer.username,
            f"{split.gross_amount:.2f}",
            f"{split.commission_amount:.2f}",
            f"{split.net_amount:.2f}",
        ])
    writer.writerow([])
    writer.writerow([
        'TOTAL', '', '',
        f"{settlement.gross_amount:.2f}",
        f"{settlement.commission_amount:.2f}",
        f"{settlement.net_amount:.2f}",
    ])

    return response
