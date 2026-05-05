"""
TC-018 management command — auto-generates pending Orders from active
RecurringOrder templates whose recurrence_day matches today (or --date).

Usage:
    python manage.py generate_recurring_orders
    python manage.py generate_recurring_orders --date 2026-05-04
    python manage.py generate_recurring_orders --all     # ignore weekday filter

Generated Orders are 'pending' — the customer still needs to check out via
the normal Stripe flow. Items where stock or availability has dropped are
skipped and reported; templates with no available items are skipped entirely.
"""

from datetime import datetime, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from orders.models import Order, OrderItem, RecurringOrder


class Command(BaseCommand):
    help = "Generate pending Orders from active RecurringOrder templates."

    def add_arguments(self, parser):
        parser.add_argument(
            '--date',
            help='Override "today" (ISO YYYY-MM-DD). Useful for demo/testing.',
        )
        parser.add_argument(
            '--all',
            action='store_true',
            help='Run for every active recurring order regardless of recurrence_day.',
        )

    def handle(self, *args, **options):
        if options['date']:
            today = datetime.fromisoformat(options['date']).date()
        else:
            today = timezone.now().date()

        weekday = today.weekday()  # 0 = Monday

        templates_qs = (
            RecurringOrder.objects
            .filter(is_active=True)
            .prefetch_related('items__product')
        )
        if not options['all']:
            templates_qs = templates_qs.filter(recurrence_day=weekday)

        templates = list(templates_qs)

        if not templates:
            self.stdout.write(self.style.WARNING(
                f"No active recurring orders for {today} ({today.strftime('%A')})."
            ))
            return

        created_count = 0
        skipped_unavailable = 0
        skipped_empty = 0

        for ro in templates:
            # Calculate next delivery date: next occurrence of delivery_day,
            # at least 2 days from `today` (matches the 48h checkout rule).
            days_ahead = (ro.delivery_day - weekday) % 7
            if days_ahead < 2:
                days_ahead += 7
            delivery_date = today + timedelta(days=days_ahead)

            # Snapshot prices and skip unavailable / out-of-stock items
            line_items = []
            running_total = Decimal('0.00')
            for ri in ro.items.select_related('product').all():
                product = ri.product
                if not product.is_available:
                    self.stdout.write(self.style.WARNING(
                        f"  [#{ro.pk}] Skipping {product.name} — unavailable."
                    ))
                    skipped_unavailable += 1
                    continue
                qty = min(ri.quantity, product.stock_quantity)
                if qty == 0:
                    self.stdout.write(self.style.WARNING(
                        f"  [#{ro.pk}] Skipping {product.name} — out of stock."
                    ))
                    skipped_unavailable += 1
                    continue
                price = product.current_price
                line_items.append({'product': product, 'quantity': qty, 'price': price})
                running_total += price * qty

            if not line_items:
                self.stdout.write(self.style.WARNING(
                    f"  [#{ro.pk}] No available items for '{ro.name or ro.pk}' — skipping order creation."
                ))
                skipped_empty += 1
                continue

            order = Order.objects.create(
                customer=ro.customer,
                total=running_total,
                status='pending',
                delivery_date=delivery_date,
                delivery_address=ro.delivery_address,
                delivery_instructions=ro.delivery_instructions,
            )
            for li in line_items:
                OrderItem.objects.create(
                    order=order,
                    product=li['product'],
                    quantity=li['quantity'],
                    price=li['price'],
                )

            ro.last_generated_at = timezone.now()
            ro.save(update_fields=['last_generated_at'])
            created_count += 1

            self.stdout.write(self.style.SUCCESS(
                f"  [#{ro.pk}] -> Order #{order.pk} "
                f"({len(line_items)} item(s), £{running_total}, delivery {delivery_date})"
            ))

        self.stdout.write(self.style.SUCCESS(
            f"\nDone. Created {created_count} order(s); "
            f"skipped {skipped_unavailable} unavailable item(s) "
            f"and {skipped_empty} empty template(s)."
        ))
