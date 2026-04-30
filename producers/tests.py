from datetime import date, timedelta
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from orders.models import Order, OrderItem, Payment, PaymentSplit, Settlement
from products.models import Product


class ProducerSettlementViewsTestCase(TestCase):
    """
    BRFN-44 / TC-012: producer-facing settlement history.
    """

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.producer = User.objects.create_user(
            username="prod1", email="p1@e.com", password="pw", role="producer"
        )
        cls.other_producer = User.objects.create_user(
            username="prod2", email="p2@e.com", password="pw", role="producer"
        )
        cls.customer = User.objects.create_user(
            username="cust", email="c@e.com", password="pw", role="customer"
        )
        cls.product = Product.objects.create(
            producer=cls.producer, name="Carrots", description="x",
            category="vegetables", price=Decimal("10.00"), stock_quantity=100,
        )

        # Two settlements for our producer in the current year
        today = date.today()
        cls.settlement_a = Settlement.objects.create(
            producer=cls.producer,
            period_start=date(today.year, 1, 6),
            period_end=date(today.year, 1, 12),
            gross_amount=Decimal("100.00"),
            commission_amount=Decimal("5.00"),
            net_amount=Decimal("95.00"),
        )
        cls.settlement_b = Settlement.objects.create(
            producer=cls.producer,
            period_start=date(today.year, 2, 3),
            period_end=date(today.year, 2, 9),
            gross_amount=Decimal("80.00"),
            commission_amount=Decimal("4.00"),
            net_amount=Decimal("76.00"),
        )
        # A settlement for someone else — must not leak into our producer's view
        cls.other_settlement = Settlement.objects.create(
            producer=cls.other_producer,
            period_start=date(today.year, 1, 6),
            period_end=date(today.year, 1, 12),
            gross_amount=Decimal("999.00"),
            commission_amount=Decimal("49.95"),
            net_amount=Decimal("949.05"),
        )

    def _make_order_with_split(self, settlement, gross="50.00", when=None):
        when = when or timezone.now()
        order = Order.objects.create(
            customer=self.customer,
            total=Decimal(gross),
            status="delivered",
            delivery_date=when.date() + timedelta(days=2),
            delivery_address="x",
        )
        OrderItem.objects.create(
            order=order, product=self.product,
            quantity=int(Decimal(gross) / Decimal("10.00")),
            price=Decimal("10.00"),
        )
        gross_d = Decimal(gross)
        payment = Payment.objects.create(
            order=order,
            stripe_session_id=f"sess_{order.id}",
            amount=gross_d,
            commission_amount=gross_d * Decimal("0.05"),
            producer_net=gross_d * Decimal("0.95"),
            currency="GBP",
            status="succeeded",
        )
        PaymentSplit.objects.create(
            payment=payment,
            producer=self.producer,
            settlement=settlement,
            gross_amount=gross_d,
            commission_amount=gross_d * Decimal("0.05"),
            net_amount=gross_d * Decimal("0.95"),
        )
        return order

    def test_list_view_shows_only_own_settlements(self):
        self.client.force_login(self.producer)
        response = self.client.get(reverse("producers:settlements_list"))
        self.assertEqual(response.status_code, 200)
        settlements = list(response.context["settlements"])
        self.assertIn(self.settlement_a, settlements)
        self.assertIn(self.settlement_b, settlements)
        self.assertNotIn(self.other_settlement, settlements)

    def test_list_view_includes_ytd_totals(self):
        self.client.force_login(self.producer)
        response = self.client.get(reverse("producers:settlements_list"))
        ytd = response.context["ytd"]
        # settlement_a (£95) + settlement_b (£76) = £171 net YTD
        self.assertEqual(ytd["net"], Decimal("171.00"))
        self.assertEqual(ytd["gross"], Decimal("180.00"))
        self.assertEqual(ytd["commission"], Decimal("9.00"))

    def test_non_producer_redirected(self):
        self.client.force_login(self.customer)
        response = self.client.get(reverse("producers:settlements_list"))
        self.assertEqual(response.status_code, 302)

    def test_detail_view_shows_contributing_orders(self):
        self._make_order_with_split(self.settlement_a, gross="50.00")
        self._make_order_with_split(self.settlement_a, gross="30.00")
        self.client.force_login(self.producer)
        response = self.client.get(
            reverse("producers:settlement_detail", args=[self.settlement_a.id])
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["splits"].count(), 2)

    def test_detail_view_blocks_other_producers(self):
        self.client.force_login(self.producer)
        response = self.client.get(
            reverse("producers:settlement_detail", args=[self.other_settlement.id])
        )
        self.assertEqual(response.status_code, 404)

    def test_csv_download_contains_breakdown(self):
        self._make_order_with_split(self.settlement_a, gross="50.00")
        self.client.force_login(self.producer)
        response = self.client.get(
            reverse("producers:settlement_csv", args=[self.settlement_a.id])
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv")
        self.assertIn("attachment", response["Content-Disposition"])
        body = response.content.decode("utf-8")
        self.assertIn("Order #", body)
        self.assertIn("Gross", body)
        self.assertIn("Commission", body)
        self.assertIn("Net", body)
        self.assertIn("50.00", body)
        self.assertIn("TOTAL", body)

    def test_csv_blocks_other_producers(self):
        self.client.force_login(self.producer)
        response = self.client.get(
            reverse("producers:settlement_csv", args=[self.other_settlement.id])
        )
        self.assertEqual(response.status_code, 404)
