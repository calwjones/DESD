"""
Aggregate the previous calendar week's PaymentSplits per producer into
Settlement records. Run weekly on Monday after the Sunday-midnight cutoff.

Usage:
    python manage.py calculate_settlements
    python manage.py calculate_settlements --week-of 2026-04-22
"""

from datetime import datetime, timedelta
from decimal import Decimal
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Sum
from orders.models import PaymentSplit, Settlement


def previous_week_bounds(reference_date):
    """Return (Mon, Sun) for the most recently completed calendar week,
    relative to reference_date. If reference_date is itself a Sunday, the
    current week is treated as not yet complete and the prior week is returned."""
    weekday = reference_date.weekday()  # Mon=0, Sun=6
    days_since_sunday = (weekday + 1) % 7 or 7
    period_end = reference_date - timedelta(days=days_since_sunday)
    period_start = period_end - timedelta(days=6)
    return period_start, period_end


def week_containing(target_date):
    """Return (Mon, Sun) of the calendar week containing target_date."""
    weekday = target_date.weekday()
    period_start = target_date - timedelta(days=weekday)
    period_end = period_start + timedelta(days=6)
    return period_start, period_end


class Command(BaseCommand):
    help = "Aggregate the week's payment splits per producer into Settlement records."

    def add_arguments(self, parser):
        parser.add_argument(
            "--week-of",
            type=str,
            default=None,
            help="Any date inside the target week (YYYY-MM-DD). Defaults to the previous completed week.",
        )

    def handle(self, *args, **options):
        if options["week_of"]:
            try:
                target = datetime.strptime(options["week_of"], "%Y-%m-%d").date()
            except ValueError:
                raise CommandError("--week-of must be YYYY-MM-DD")
            period_start, period_end = week_containing(target)
        else:
            period_start, period_end = previous_week_bounds(datetime.now().date())

        self.stdout.write(f"Settling week {period_start} → {period_end}")

        # Aggregate per producer over PaymentSplits whose Payment is succeeded
        # and whose Order has been delivered (TC-012: only delivered orders count).
        splits = (
            PaymentSplit.objects
            .filter(
                payment__status="succeeded",
                payment__order__status="delivered",
                payment__created_at__date__gte=period_start,
                payment__created_at__date__lte=period_end,
            )
            .values("producer")
            .annotate(
                gross=Sum("gross_amount"),
                commission=Sum("commission_amount"),
                net=Sum("net_amount"),
            )
        )

        created = 0
        updated = 0
        for row in splits:
            obj, was_created = Settlement.objects.update_or_create(
                producer_id=row["producer"],
                period_start=period_start,
                defaults={
                    "period_end": period_end,
                    "gross_amount": row["gross"] or Decimal("0"),
                    "commission_amount": row["commission"] or Decimal("0"),
                    "net_amount": row["net"] or Decimal("0"),
                },
            )
            if was_created:
                created += 1
            else:
                updated += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Settlements: {created} created, {updated} updated."
            )
        )
