from decimal import Decimal
from datetime import datetime, date, timedelta
from io import StringIO
from unittest.mock import patch
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from products.models import Product
from .forms import CheckoutForm
from .management.commands.calculate_settlements import previous_week_bounds, week_containing
from .models import Order, OrderItem, Payment, PaymentSplit, Settlement
from .services import calculate_commission_split
from .validators import validate_delivery_date


class DeliveryValidationTestCase(TestCase):
    """
    Test suite for BRFN-35: 48-hour delivery window validation.
    """
    
    def test_delivery_date_tomorrow_rejected(self):
        """Delivery date of tomorrow (24 hours) should be rejected"""
        tomorrow = timezone.now().date() + timedelta(days=1)
        
        with self.assertRaises(ValidationError):
            validate_delivery_date(tomorrow)
    
    def test_delivery_date_today_rejected(self):
        """Delivery date of today should be rejected"""
        today = timezone.now().date()
        
        with self.assertRaises(ValidationError):
            validate_delivery_date(today)
    
    def test_delivery_date_48_hours_accepted(self):
        """Delivery date exactly 48 hours away should be accepted"""
        valid_date = timezone.now().date() + timedelta(days=2)
        
        try:
            validate_delivery_date(valid_date)
        except ValidationError:
            self.fail("validate_delivery_date raised ValidationError unexpectedly")
    
    def test_delivery_date_one_week_accepted(self):
        """Delivery date one week in future should be accepted"""
        future_date = timezone.now().date() + timedelta(days=7)
        
        try:
            validate_delivery_date(future_date)
        except ValidationError:
            self.fail("validate_delivery_date raised ValidationError unexpectedly")


class CheckoutFormTestCase(TestCase):
    """
    Test suite for CheckoutForm validation.
    """
    
    def test_form_rejects_too_soon_delivery(self):
        """Form should reject delivery date less than 48 hours"""
        tomorrow = timezone.now().date() + timedelta(days=1)
        
        form = CheckoutForm(data={
            'delivery_address': '123 Test Street, Bristol, BS1 1AB',
            'delivery_date': tomorrow
        })
        
        self.assertFalse(form.is_valid())
        self.assertIn('delivery_date', form.errors)
    
    def test_form_accepts_valid_delivery_date(self):
        """Form should accept delivery date 48+ hours away"""
        valid_date = timezone.now().date() + timedelta(days=3)
        
        form = CheckoutForm(data={
            'delivery_address': '123 Test Street, Bristol, BS1 1AB',
            'delivery_date': valid_date
        })
        
        self.assertTrue(form.is_valid())
    
    def test_form_requires_delivery_address(self):
        """Delivery address should be required"""
        valid_date = timezone.now().date() + timedelta(days=3)
        
        form = CheckoutForm(data={
            'delivery_address': '',
            'delivery_date': valid_date
        })
        
        self.assertFalse(form.is_valid())
        self.assertIn('delivery_address', form.errors)
    
    def test_form_requires_delivery_date(self):
        """Delivery date should be required"""
        form = CheckoutForm(data={
            'delivery_address': '123 Test Street, Bristol, BS1 1AB',
            'delivery_date': ''
        })
        
        self.assertFalse(form.is_valid())
        self.assertIn('delivery_date', form.errors)
    
    def test_form_complete_valid_data(self):
        """Form should accept complete valid data"""
        valid_date = timezone.now().date() + timedelta(days=5)
        
        form = CheckoutForm(data={
            'delivery_address': '123 Test Street, Bristol, BS1 1AB',
            'delivery_date': valid_date
        })
        
        self.assertTrue(form.is_valid())
        self.assertEqual(
            form.cleaned_data['delivery_address'],
            '123 Test Street, Bristol, BS1 1AB'
        )
        self.assertEqual(form.cleaned_data['delivery_date'], valid_date)


class _FakeStripeSession(dict):
    """Mimics Stripe's StripeObject — supports both attribute and dict access."""

    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError as exc:
            raise AttributeError(key) from exc


class PaymentModelTestCase(TestCase):
    """
    BRFN-39: Payment model is populated and transitions correctly through
    the checkout/webhook/cancel flows. Backs TC-007 acceptance criterion
    'Payment transaction is recorded'.
    """

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.customer = User.objects.create_user(
            username="customer1", email="c@example.com", password="pw", role="customer"
        )
        cls.producer = User.objects.create_user(
            username="producer1", email="p@example.com", password="pw", role="producer"
        )
        cls.product = Product.objects.create(
            producer=cls.producer,
            name="Organic Carrots",
            description="Fresh",
            category="vegetables",
            price=Decimal("10.00"),
            stock_quantity=50,
        )

    def _make_order(self, session_id="sess_test_123"):
        order = Order.objects.create(
            customer=self.customer,
            total=Decimal("100.00"),
            status="pending",
            delivery_date=timezone.now().date() + timedelta(days=3),
            delivery_address="1 Test St, Bristol, BS1 1AB",
            stripe_session_id=session_id,
        )
        OrderItem.objects.create(
            order=order, product=self.product, quantity=10, price=Decimal("10.00")
        )
        Payment.objects.create(
            order=order,
            stripe_session_id=session_id,
            amount=order.total,
            currency="GBP",
            status="pending",
        )
        return order

    def test_payment_record_created_with_pending_status(self):
        order = self._make_order()
        payment = order.payment
        self.assertEqual(payment.status, "pending")
        self.assertEqual(payment.amount, Decimal("100.00"))
        self.assertEqual(payment.currency, "GBP")
        self.assertEqual(payment.stripe_session_id, "sess_test_123")
        self.assertEqual(payment.stripe_payment_intent_id, "")

    @patch("orders.views.stripe.checkout.Session.retrieve")
    def test_payment_success_marks_payment_succeeded(self, mock_retrieve):
        order = self._make_order()
        mock_retrieve.return_value = _FakeStripeSession({
            "id": "sess_test_123",
            "payment_status": "paid",
            "payment_intent": "pi_test_999",
        })
        self.client.force_login(self.customer)
        with patch("orders.views._send_confirmation_emails"):
            self.client.get(
                reverse("payment_success") + "?session_id=sess_test_123"
            )
        order.refresh_from_db()
        payment = order.payment
        self.assertEqual(order.status, "confirmed")
        self.assertEqual(payment.status, "succeeded")
        self.assertEqual(payment.stripe_payment_intent_id, "pi_test_999")

    @patch("orders.views.stripe.Webhook.construct_event")
    def test_webhook_marks_payment_succeeded(self, mock_construct):
        order = self._make_order(session_id="sess_webhook_1")
        mock_construct.return_value = {
            "type": "checkout.session.completed",
            "data": {
                "object": _FakeStripeSession({
                    "id": "sess_webhook_1",
                    "payment_intent": "pi_webhook_1",
                    "metadata": {"order_id": str(order.id)},
                })
            },
        }
        self.client.post(
            reverse("stripe_webhook"),
            data="{}",
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="t=1,v1=fake",
        )
        order.refresh_from_db()
        payment = order.payment
        self.assertEqual(order.status, "confirmed")
        self.assertEqual(payment.status, "succeeded")
        self.assertEqual(payment.stripe_payment_intent_id, "pi_webhook_1")

    def test_payment_cancel_marks_payment_failed(self):
        order = self._make_order(session_id="sess_cancel_1")
        self.client.force_login(self.customer)
        self.client.get(reverse("payment_cancel") + f"?order_id={order.id}")
        order.refresh_from_db()
        payment = order.payment
        self.assertEqual(order.status, "cancelled")
        self.assertEqual(payment.status, "failed")


class CommissionCalculationTestCase(TestCase):
    """
    BRFN-41 / TC-025: 5% network commission, 95% producer net.
    Numbers locked to the worked examples in the test case document.
    """

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.customer = User.objects.create_user(
            username="buyer", email="b@example.com", password="pw", role="customer"
        )
        cls.producer1 = User.objects.create_user(
            username="prod1", email="p1@example.com", password="pw", role="producer"
        )
        cls.producer2 = User.objects.create_user(
            username="prod2", email="p2@example.com", password="pw", role="producer"
        )
        cls.product1 = Product.objects.create(
            producer=cls.producer1,
            name="Carrots",
            description="Fresh",
            category="vegetables",
            price=Decimal("10.00"),
            stock_quantity=100,
        )
        cls.product2 = Product.objects.create(
            producer=cls.producer2,
            name="Milk",
            description="Whole",
            category="dairy",
            price=Decimal("10.00"),
            stock_quantity=100,
        )

    def _make_order(self, total, items):
        """items: list of (product, quantity, price)."""
        order = Order.objects.create(
            customer=self.customer,
            total=Decimal(total),
            status="pending",
            delivery_date=timezone.now().date() + timedelta(days=3),
            delivery_address="1 Test St, Bristol, BS1 1AB",
        )
        for product, qty, price in items:
            OrderItem.objects.create(
                order=order, product=product, quantity=qty, price=Decimal(price)
            )
        return order

    def test_single_vendor_100_pound_order(self):
        """TC-025: £100 order → £5.00 commission, £95.00 producer net."""
        order = self._make_order(
            "100.00", [(self.product1, 10, "10.00")]
        )
        result = calculate_commission_split(order)
        self.assertEqual(result["total_gross"], Decimal("100.00"))
        self.assertEqual(result["total_commission"], Decimal("5.00"))
        self.assertEqual(result["total_net"], Decimal("95.00"))
        self.assertEqual(len(result["splits"]), 1)
        split = result["splits"][0]
        self.assertEqual(split["producer"], self.producer1)
        self.assertEqual(split["gross"], Decimal("100.00"))
        self.assertEqual(split["commission"], Decimal("5.00"))
        self.assertEqual(split["net"], Decimal("95.00"))

    def test_multi_vendor_150_pound_order(self):
        """TC-025: £150 order (P1: £80, P2: £70) → commission £7.50, P1 £76.00, P2 £66.50."""
        order = self._make_order(
            "150.00",
            [
                (self.product1, 8, "10.00"),  # P1: £80
                (self.product2, 7, "10.00"),  # P2: £70
            ],
        )
        result = calculate_commission_split(order)
        self.assertEqual(result["total_gross"], Decimal("150.00"))
        self.assertEqual(result["total_commission"], Decimal("7.50"))
        self.assertEqual(result["total_net"], Decimal("142.50"))
        self.assertEqual(len(result["splits"]), 2)

        by_producer = {s["producer"].id: s for s in result["splits"]}
        p1 = by_producer[self.producer1.id]
        p2 = by_producer[self.producer2.id]
        self.assertEqual(p1["gross"], Decimal("80.00"))
        self.assertEqual(p1["commission"], Decimal("4.00"))
        self.assertEqual(p1["net"], Decimal("76.00"))
        self.assertEqual(p2["gross"], Decimal("70.00"))
        self.assertEqual(p2["commission"], Decimal("3.50"))
        self.assertEqual(p2["net"], Decimal("66.50"))

    def test_rounding_to_two_decimal_places(self):
        """TC-025 acceptance: payment calculations are accurate to 2dp."""
        order = self._make_order(
            "33.33", [(self.product1, 1, "33.33")]
        )
        result = calculate_commission_split(order)
        self.assertEqual(result["total_commission"], Decimal("1.67"))
        self.assertEqual(result["total_net"], Decimal("31.66"))

    def test_payment_split_rows_persisted(self):
        """Wired into the checkout flow: PaymentSplit rows match the calculation."""
        order = self._make_order(
            "150.00",
            [
                (self.product1, 8, "10.00"),
                (self.product2, 7, "10.00"),
            ],
        )
        split = calculate_commission_split(order)
        payment = Payment.objects.create(
            order=order,
            stripe_session_id="sess_x",
            amount=order.total,
            commission_amount=split["total_commission"],
            producer_net=split["total_net"],
            currency="GBP",
            status="pending",
        )
        for s in split["splits"]:
            PaymentSplit.objects.create(
                payment=payment,
                producer=s["producer"],
                gross_amount=s["gross"],
                commission_amount=s["commission"],
                net_amount=s["net"],
            )

        self.assertEqual(payment.splits.count(), 2)
        self.assertEqual(payment.commission_amount, Decimal("7.50"))
        self.assertEqual(payment.producer_net, Decimal("142.50"))
        self.assertEqual(
            payment.splits.get(producer=self.producer1).net_amount,
            Decimal("76.00"),
        )


class WeekBoundsTestCase(TestCase):
    """BRFN-42: calendar week (Mon-Sun) bounds calculation."""

    def test_previous_week_from_monday(self):
        # Mon 2026-04-27 → previous week is Mon 04-20 to Sun 04-26
        start, end = previous_week_bounds(date(2026, 4, 27))
        self.assertEqual(start, date(2026, 4, 20))
        self.assertEqual(end, date(2026, 4, 26))

    def test_previous_week_from_midweek(self):
        # Wed 2026-04-29 → previous week ended Sun 04-26
        start, end = previous_week_bounds(date(2026, 4, 29))
        self.assertEqual(start, date(2026, 4, 20))
        self.assertEqual(end, date(2026, 4, 26))

    def test_previous_week_from_sunday(self):
        # Sun 2026-04-26 — current week not yet complete, returns prior week
        start, end = previous_week_bounds(date(2026, 4, 26))
        self.assertEqual(start, date(2026, 4, 13))
        self.assertEqual(end, date(2026, 4, 19))

    def test_week_containing_target(self):
        # Wed 2026-04-22 → week is Mon 04-20 to Sun 04-26
        start, end = week_containing(date(2026, 4, 22))
        self.assertEqual(start, date(2026, 4, 20))
        self.assertEqual(end, date(2026, 4, 26))


class SettlementCalculationTestCase(TestCase):
    """
    BRFN-42 / TC-012: weekly producer settlements aggregated from
    PaymentSplits whose payments succeeded and whose orders were delivered.
    """

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.customer = User.objects.create_user(
            username="buyer", email="b@e.com", password="pw", role="customer"
        )
        cls.producer1 = User.objects.create_user(
            username="prod1", email="p1@e.com", password="pw", role="producer"
        )
        cls.producer2 = User.objects.create_user(
            username="prod2", email="p2@e.com", password="pw", role="producer"
        )
        cls.product1 = Product.objects.create(
            producer=cls.producer1, name="Carrots", description="x",
            category="vegetables", price=Decimal("10.00"), stock_quantity=100,
        )
        cls.product2 = Product.objects.create(
            producer=cls.producer2, name="Milk", description="x",
            category="dairy", price=Decimal("10.00"), stock_quantity=100,
        )

    def _make_paid_delivered_order(self, items, total, when, order_status="delivered"):
        """items: list of (product, qty, price). when: aware datetime for Payment.created_at."""
        order = Order.objects.create(
            customer=self.customer,
            total=Decimal(total),
            status=order_status,
            delivery_date=when.date() + timedelta(days=2),
            delivery_address="1 Test St",
        )
        for product, qty, price in items:
            OrderItem.objects.create(
                order=order, product=product, quantity=qty, price=Decimal(price)
            )
        split = calculate_commission_split(order)
        payment = Payment.objects.create(
            order=order,
            stripe_session_id=f"sess_{order.id}",
            amount=order.total,
            commission_amount=split["total_commission"],
            producer_net=split["total_net"],
            currency="GBP",
            status="succeeded",
        )
        for s in split["splits"]:
            PaymentSplit.objects.create(
                payment=payment,
                producer=s["producer"],
                gross_amount=s["gross"],
                commission_amount=s["commission"],
                net_amount=s["net"],
            )
        # Override auto_now_add so the payment lands in the target week
        Payment.objects.filter(pk=payment.pk).update(created_at=when)
        return order

    def _aware(self, year, month, day, hour=12):
        return timezone.make_aware(datetime(year, month, day, hour, 0))

    def test_single_producer_aggregates_two_orders(self):
        """Two delivered, paid orders for one producer → one Settlement summing them."""
        # Week of Mon 2026-04-20 to Sun 2026-04-26
        self._make_paid_delivered_order(
            [(self.product1, 5, "10.00")], "50.00", self._aware(2026, 4, 21)
        )
        self._make_paid_delivered_order(
            [(self.product1, 3, "10.00")], "30.00", self._aware(2026, 4, 24)
        )
        out = StringIO()
        call_command("calculate_settlements", "--week-of", "2026-04-22", stdout=out)

        settlement = Settlement.objects.get(producer=self.producer1)
        self.assertEqual(settlement.period_start, date(2026, 4, 20))
        self.assertEqual(settlement.period_end, date(2026, 4, 26))
        self.assertEqual(settlement.gross_amount, Decimal("80.00"))
        self.assertEqual(settlement.commission_amount, Decimal("4.00"))
        self.assertEqual(settlement.net_amount, Decimal("76.00"))
        self.assertEqual(settlement.status, "pending")

    def test_undelivered_orders_excluded(self):
        """Orders not yet delivered should not appear in any settlement (TC-012)."""
        self._make_paid_delivered_order(
            [(self.product1, 5, "10.00")], "50.00",
            self._aware(2026, 4, 21), order_status="dispatched",
        )
        call_command("calculate_settlements", "--week-of", "2026-04-22", stdout=StringIO())
        self.assertFalse(Settlement.objects.filter(producer=self.producer1).exists())

    def test_multi_vendor_order_splits_per_producer(self):
        """A single multi-vendor order generates one Settlement per producer."""
        self._make_paid_delivered_order(
            [
                (self.product1, 8, "10.00"),  # P1 £80
                (self.product2, 7, "10.00"),  # P2 £70
            ],
            "150.00",
            self._aware(2026, 4, 23),
        )
        call_command("calculate_settlements", "--week-of", "2026-04-22", stdout=StringIO())

        s1 = Settlement.objects.get(producer=self.producer1)
        s2 = Settlement.objects.get(producer=self.producer2)
        self.assertEqual(s1.net_amount, Decimal("76.00"))
        self.assertEqual(s2.net_amount, Decimal("66.50"))
        self.assertEqual(s1.commission_amount, Decimal("4.00"))
        self.assertEqual(s2.commission_amount, Decimal("3.50"))

    def test_payments_outside_week_excluded(self):
        """Payments outside the target week are not aggregated."""
        # In-week: Mon 04-20
        self._make_paid_delivered_order(
            [(self.product1, 5, "10.00")], "50.00", self._aware(2026, 4, 20)
        )
        # Out-of-week: Sun 04-19 (prior week) and Mon 04-27 (next week)
        self._make_paid_delivered_order(
            [(self.product1, 5, "10.00")], "50.00", self._aware(2026, 4, 19)
        )
        self._make_paid_delivered_order(
            [(self.product1, 5, "10.00")], "50.00", self._aware(2026, 4, 27)
        )
        call_command("calculate_settlements", "--week-of", "2026-04-22", stdout=StringIO())
        settlement = Settlement.objects.get(
            producer=self.producer1, period_start=date(2026, 4, 20)
        )
        self.assertEqual(settlement.gross_amount, Decimal("50.00"))

    def test_command_is_idempotent(self):
        """Re-running the command updates the existing Settlement instead of duplicating."""
        self._make_paid_delivered_order(
            [(self.product1, 5, "10.00")], "50.00", self._aware(2026, 4, 21)
        )
        call_command("calculate_settlements", "--week-of", "2026-04-22", stdout=StringIO())
        call_command("calculate_settlements", "--week-of", "2026-04-22", stdout=StringIO())
        self.assertEqual(
            Settlement.objects.filter(producer=self.producer1).count(), 1
        )