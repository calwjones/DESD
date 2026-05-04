"""
Django management command to seed the database with synthetic order data.

Usage:
    1. Put purchase_history.csv in the project root (same level as manage.py)
    2. Run: python manage.py seed_orders
"""

import csv
from datetime import datetime
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from products.models import Product
from orders.models import Order, OrderItem
from producers.models import ProducerProfile

User = get_user_model()

DATE_FORMAT = '%d/%m/%Y'


def _parse_date(raw):
    return datetime.strptime(raw, DATE_FORMAT).date()


class Command(BaseCommand):
    help = 'Seed database with synthetic order data from purchase_history.csv'


    def _reset_sequences(self, table_specs):
        from django.db import connection
        with connection.cursor() as cursor:
            for table, pk in table_specs:
                cursor.execute(f"""
                    SELECT setval(
                        pg_get_serial_sequence('{table}', '{pk}'),
                        COALESCE((SELECT MAX({pk}) FROM {table}), 0) + 1,
                        false
                    );
                """)

    def add_arguments(self, parser):
        parser.add_argument(
            '--csv',
            default='purchase_history.csv',
            help='Path to the CSV file (default: purchase_history.csv)'
        )

    def handle(self, *args, **options):
        csv_path = options['csv']

        with open(csv_path, 'r') as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        self.stdout.write(f'Loaded {len(rows)} rows from {csv_path}')

        producer_ids = set(int(r['producer_id']) for r in rows)
        producers_created = 0

        producer_names = {
            2: 'fredsfarm',
            3: 'greenvalley',
            4: 'sunshineorganics',
            5: 'riverside',
            6: 'hilltop',
            7: 'orchardlane',
            8: 'meadowfresh',
            9: 'thepreservery',
            10: 'wildroots',
        }

        producer_business_names = {
            5: 'Riverside Growers',
            6: 'Hill Top Bakery',
            7: 'Orchard Lane Farm',
            8: 'Meadow Fresh',
            9: 'The Preservery',
            10: 'Wild Roots',
        }

        for pid in producer_ids:
            if not User.objects.filter(pk=pid).exists():
                username = producer_names.get(pid, f'producer_{pid}')
                User.objects.create_user(
                    pk=pid,
                    username=username,
                    email=f'{username}@brfn.local',
                    password='testpass123',
                    first_name=username.replace('_', ' ').title(),
                    last_name='Producer',
                    role='producer',
                )
                producers_created += 1

        self.stdout.write(f'Producers: {producers_created} created, {len(producer_ids) - producers_created} already existed')

        profiles_created = 0
        for pid in producer_ids:
            user = User.objects.get(pk=pid)
            _, created = ProducerProfile.objects.get_or_create(
                user=user,
                defaults={
                    'business_name': producer_business_names.get(pid, f'Producer {pid}'),
                    'bio': 'Local producer supplying fresh produce to the Bristol region.',
                    'contact_email': f'{producer_names.get(pid, f"producer_{pid}")}@brfn.local',
                    'postcode': 'BS1 1AA',
                }
            )
            if created:
                profiles_created += 1

        self.stdout.write(f'Producer profiles: {profiles_created} created, {len(producer_ids) - profiles_created} already existed')

        customer_ids = set(int(r['customer_id']) for r in rows)
        customers_created = 0

        for cid in customer_ids:
            if not User.objects.filter(pk=cid).exists():
                User.objects.create_user(
                    pk=cid,
                    username=f'customer_{cid}',
                    email=f'customer_{cid}@brfn.local',
                    password='testpass123',
                    first_name='Customer',
                    last_name=str(cid),
                    role='customer',
                )
                customers_created += 1

        self.stdout.write(f'Customers: {customers_created} created, {len(customer_ids) - customers_created} already existed')

        seen_products = {}
        for r in rows:
            pid = int(r['product_id'])
            if pid not in seen_products:
                seen_products[pid] = {
                    'name': r['product_name'],
                    'category': r['category'],
                    'price': r['price'],
                    'producer_id': int(r['producer_id']),
                }

        products_created = 0
        for pid, pdata in seen_products.items():
            if not Product.objects.filter(pk=pid).exists():
                Product.objects.create(
                    pk=pid,
                    name=pdata['name'],
                    description=f"Local {pdata['category']} produce from the Bristol region.",
                    category=pdata['category'],
                    price=pdata['price'],
                    producer_id=pdata['producer_id'],
                    stock_quantity=50,
                    is_available=True,
                )
                products_created += 1

        self.stdout.write(f'Products: {products_created} created, {len(seen_products) - products_created} already existed')

        orders_by_id = {}
        for r in rows:
            oid = int(r['order_id'])
            if oid not in orders_by_id:
                orders_by_id[oid] = {
                    'customer_id': int(r['customer_id']),
                    'order_date': r['order_date'],
                    'delivery_date': r['delivery_date'],
                    'order_total': r['order_total'],
                    'status': r['status'],
                    'items': [],
                }
            orders_by_id[oid]['items'].append({
                'product_id': int(r['product_id']),
                'quantity': int(r['quantity']),
                'price': r['price'],
            })

        orders_created = 0
        items_created = 0

        for oid, odata in orders_by_id.items():
            if Order.objects.filter(pk=oid).exists():
                continue

            order = Order.objects.create(
                pk=oid,
                customer_id=odata['customer_id'],
                total=odata['order_total'],
                status=odata['status'],
                delivery_date=_parse_date(odata['delivery_date']),
                delivery_address='Bristol',
            )
            Order.objects.filter(pk=order.pk).update(
                created_at=_parse_date(odata['order_date'])
            )
            orders_created += 1

            for item in odata['items']:
                OrderItem.objects.create(
                    order=order,
                    product_id=item['product_id'],
                    quantity=item['quantity'],
                    price=item['price'],
                    is_packed=True,
                )
                items_created += 1

        self.stdout.write(self.style.SUCCESS(
            f'\nDone! Created {orders_created} orders with {items_created} items.'
        ))
        self.stdout.write(self.style.SUCCESS(
            f'Total in DB: {Order.objects.count()} orders, {OrderItem.objects.count()} items'
        ))

        self._reset_sequences([
            ('orders_order', 'id'),
            ('orders_orderitem', 'id'),
            ('products_product', 'id'),
            ('accounts_customuser', 'id'),
            ('producers_producerprofile', 'id'),
        ])

        self.stdout.write(self.style.SUCCESS('Sequences reset'))
