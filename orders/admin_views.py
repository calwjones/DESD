"""
Admin-only commission reporting (TC-025).

Network sustainability + financial compliance reporting on the 5%
commission across all orders. Admin/staff users only — non-staff get a 404
to avoid leaking the existence of these routes.
"""

import csv
from datetime import date, timedelta
from decimal import Decimal
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Sum
from django.http import Http404, HttpResponse
from django.shortcuts import render

from .models import Payment, PaymentSplit
from .services import COMMISSION_RATE


def _staff_required(view):
    """Restrict access to is_staff users; deny with 404 (not 302) for opacity."""
    @login_required
    def wrapped(request, *args, **kwargs):
        if not request.user.is_staff:
            raise Http404
        return view(request, *args, **kwargs)
    return wrapped


def _parse_date(raw, default):
    if not raw:
        return default
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return default


def _filtered_payments(start, end):
    return Payment.objects.filter(
        status="succeeded",
        created_at__date__gte=start,
        created_at__date__lte=end,
    ).select_related("order__customer").order_by("-created_at")


@_staff_required
def commission_report(request):
    today = date.today()
    default_start = today - timedelta(days=14)
    start = _parse_date(request.GET.get("start"), default_start)
    end = _parse_date(request.GET.get("end"), today)

    payments = _filtered_payments(start, end)

    rows = []
    for payment in payments:
        producer_splits = list(
            PaymentSplit.objects
            .filter(payment=payment)
            .select_related("producer")
        )
        rows.append({
            "payment": payment,
            "splits": producer_splits,
        })

    period_totals = payments.aggregate(
        gross=Sum("amount"),
        commission=Sum("commission_amount"),
        net=Sum("producer_net"),
    )

    ytd_totals = (
        Payment.objects
        .filter(status="succeeded", created_at__year=today.year)
        .aggregate(
            gross=Sum("amount"),
            commission=Sum("commission_amount"),
            net=Sum("producer_net"),
        )
    )

    context = {
        "start": start,
        "end": end,
        "rows": rows,
        "order_count": payments.count(),
        "period_totals": {
            "gross": period_totals["gross"] or Decimal("0"),
            "commission": period_totals["commission"] or Decimal("0"),
            "net": period_totals["net"] or Decimal("0"),
        },
        "ytd_totals": {
            "year": today.year,
            "gross": ytd_totals["gross"] or Decimal("0"),
            "commission": ytd_totals["commission"] or Decimal("0"),
            "net": ytd_totals["net"] or Decimal("0"),
        },
        "commission_rate_pct": int(COMMISSION_RATE * 100),
    }
    return render(request, "orders/commission_report.html", context)


@_staff_required
def commission_report_csv(request):
    today = date.today()
    default_start = today - timedelta(days=14)
    start = _parse_date(request.GET.get("start"), default_start)
    end = _parse_date(request.GET.get("end"), today)

    payments = _filtered_payments(start, end)

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = (
        f'attachment; filename="commission_report_{start}_{end}.csv"'
    )
    writer = csv.writer(response)
    writer.writerow([
        "Order #", "Date", "Customer", "Producer",
        "Order Total (£)", "Producer Gross (£)", "Commission (£)", "Producer Net (£)",
        "Payment Status",
    ])

    grand_gross = Decimal("0")
    grand_commission = Decimal("0")
    grand_net = Decimal("0")
    for payment in payments:
        order = payment.order
        for split in payment.splits.select_related("producer"):
            writer.writerow([
                order.id,
                payment.created_at.date().isoformat(),
                order.customer.username,
                split.producer.username,
                f"{payment.amount:.2f}",
                f"{split.gross_amount:.2f}",
                f"{split.commission_amount:.2f}",
                f"{split.net_amount:.2f}",
                payment.status,
            ])
        grand_gross += payment.amount
        grand_commission += payment.commission_amount
        grand_net += payment.producer_net

    writer.writerow([])
    writer.writerow([
        "TOTAL", "", "", "",
        f"{grand_gross:.2f}", "",
        f"{grand_commission:.2f}",
        f"{grand_net:.2f}",
        "",
    ])
    return response
