from decimal import Decimal
from datetime import datetime, date, timedelta
from io import StringIO
from unittest.mock import patch
from django.core.management import call_command
from django.test import TestCase, RequestFactory
from django.urls import reverse
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from products.models import Product
from .forms import CheckoutForm
from .management.commands.calculate_settlements import previous_week_bounds, week_containing
from .models import (
    Order,
    OrderItem,
    Payment,
    PaymentSplit,
    RecurringOrder,
    RecurringOrderItem,
    Settlement,
)
from delivery.models import Delivery
from .services import calculate_commission_split
from .validators import validate_delivery_date



from orders.cart import Cart 
from products.models import Product

User = get_user_model()

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
            'postcode': 'BS1 1AB',
            'delivery_address': '123 Test Street, Bristol',
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
            'postcode': 'BS1 1AB',
            'delivery_address': '123 Test Street, Bristol',
            'delivery_date': valid_date
        })
        
        self.assertTrue(form.is_valid())
        self.assertEqual(
            form.cleaned_data['delivery_address'],
            '123 Test Street, Bristol'
        )
        self.assertEqual(form.cleaned_data['postcode'], 'BS1 1AB')
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

    def test_splits_linked_to_settlement(self):
        """BRFN-43: each contributing PaymentSplit gets a back-link to its Settlement."""
        order_a = self._make_paid_delivered_order(
            [(self.product1, 5, "10.00")], "50.00", self._aware(2026, 4, 21)
        )
        order_b = self._make_paid_delivered_order(
            [(self.product1, 3, "10.00")], "30.00", self._aware(2026, 4, 24)
        )
        call_command("calculate_settlements", "--week-of", "2026-04-22", stdout=StringIO())

        settlement = Settlement.objects.get(producer=self.producer1)
        split_a = order_a.payment.splits.get(producer=self.producer1)
        split_b = order_b.payment.splits.get(producer=self.producer1)
        self.assertEqual(split_a.settlement, settlement)
        self.assertEqual(split_b.settlement, settlement)
        self.assertEqual(settlement.splits.count(), 2)

    def test_multi_vendor_splits_linked_to_correct_settlements(self):
        """BRFN-43: in a multi-vendor order, each producer's split links to their own Settlement."""
        order = self._make_paid_delivered_order(
            [
                (self.product1, 8, "10.00"),
                (self.product2, 7, "10.00"),
            ],
            "150.00",
            self._aware(2026, 4, 23),
        )
        call_command("calculate_settlements", "--week-of", "2026-04-22", stdout=StringIO())

        s1 = Settlement.objects.get(producer=self.producer1)
        s2 = Settlement.objects.get(producer=self.producer2)
        split1 = order.payment.splits.get(producer=self.producer1)
        split2 = order.payment.splits.get(producer=self.producer2)
        self.assertEqual(split1.settlement, s1)
        self.assertEqual(split2.settlement, s2)

    def test_undelivered_splits_not_linked(self):
        """Splits from undelivered orders are not aggregated and have no settlement link."""
        order = self._make_paid_delivered_order(
            [(self.product1, 5, "10.00")], "50.00",
            self._aware(2026, 4, 21), order_status="dispatched",
        )
        call_command("calculate_settlements", "--week-of", "2026-04-22", stdout=StringIO())
        split = order.payment.splits.get(producer=self.producer1)
        self.assertIsNone(split.settlement)


class AdminCommissionReportTestCase(TestCase):
    """
    TC-025: admin financial reporting on the 5% network commission across orders.
    """

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.admin = User.objects.create_user(
            username="admin1", email="a@e.com", password="pw", role="customer", is_staff=True,
        )
        cls.customer = User.objects.create_user(
            username="cust", email="c@e.com", password="pw", role="customer",
        )
        cls.producer1 = User.objects.create_user(
            username="prod1", email="p1@e.com", password="pw", role="producer",
        )
        cls.producer2 = User.objects.create_user(
            username="prod2", email="p2@e.com", password="pw", role="producer",
        )
        cls.product1 = Product.objects.create(
            producer=cls.producer1, name="A", description="x",
            category="vegetables", price=Decimal("10.00"), stock_quantity=100,
        )
        cls.product2 = Product.objects.create(
            producer=cls.producer2, name="B", description="x",
            category="dairy", price=Decimal("10.00"), stock_quantity=100,
        )

    def _create_payment(self, total, items, when, status="succeeded"):
        order = Order.objects.create(
            customer=self.customer,
            total=Decimal(total),
            status="delivered",
            delivery_date=when.date() + timedelta(days=2),
            delivery_address="x",
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
            status=status,
        )
        for s in split["splits"]:
            PaymentSplit.objects.create(
                payment=payment,
                producer=s["producer"],
                gross_amount=s["gross"],
                commission_amount=s["commission"],
                net_amount=s["net"],
            )
        Payment.objects.filter(pk=payment.pk).update(created_at=when)
        return payment

    def _aware(self, year, month, day):
        return timezone.make_aware(datetime(year, month, day, 12, 0))

    def test_non_staff_gets_404(self):
        self.client.force_login(self.customer)
        response = self.client.get(reverse("commission_report"))
        self.assertEqual(response.status_code, 404)

    def test_anonymous_redirected_to_login(self):
        response = self.client.get(reverse("commission_report"))
        self.assertEqual(response.status_code, 302)

    def test_period_totals_match_tc025_examples(self):
        """£100 single + £150 multi-vendor → totals match TC-025 worked numbers."""
        self._create_payment(
            "100.00", [(self.product1, 10, "10.00")], self._aware(2026, 4, 21)
        )
        self._create_payment(
            "150.00",
            [
                (self.product1, 8, "10.00"),
                (self.product2, 7, "10.00"),
            ],
            self._aware(2026, 4, 23),
        )
        self.client.force_login(self.admin)
        response = self.client.get(
            reverse("commission_report") + "?start=2026-04-20&end=2026-04-26"
        )
        self.assertEqual(response.status_code, 200)
        totals = response.context["period_totals"]
        self.assertEqual(totals["gross"], Decimal("250.00"))
        self.assertEqual(totals["commission"], Decimal("12.50"))
        self.assertEqual(totals["net"], Decimal("237.50"))
        self.assertEqual(response.context["order_count"], 2)

    def test_date_range_filter_excludes_payments_outside(self):
        self._create_payment(
            "100.00", [(self.product1, 10, "10.00")], self._aware(2026, 4, 21)
        )
        self._create_payment(
            "50.00", [(self.product1, 5, "10.00")], self._aware(2026, 5, 5)
        )
        self.client.force_login(self.admin)
        response = self.client.get(
            reverse("commission_report") + "?start=2026-04-20&end=2026-04-26"
        )
        self.assertEqual(response.context["order_count"], 1)
        self.assertEqual(response.context["period_totals"]["gross"], Decimal("100.00"))

    def test_csv_export_includes_per_producer_rows(self):
        self._create_payment(
            "150.00",
            [
                (self.product1, 8, "10.00"),
                (self.product2, 7, "10.00"),
            ],
            self._aware(2026, 4, 23),
        )
        self.client.force_login(self.admin)
        response = self.client.get(
            reverse("commission_report_csv") + "?start=2026-04-20&end=2026-04-26"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv")
        body = response.content.decode("utf-8")
        # Both producers appear as rows
        self.assertIn("prod1", body)
        self.assertIn("prod2", body)
        # Worked numbers from TC-025
        self.assertIn("76.00", body)
        self.assertIn("66.50", body)
        self.assertIn("TOTAL", body)

    def test_csv_blocks_non_staff(self):
        self.client.force_login(self.customer)
        response = self.client.get(reverse("commission_report_csv"))
        self.assertEqual(response.status_code, 404)




class CartTestCase(TestCase):
    """
    Test suite for TC-006: shopping cart functionality.
    Covers add, remove, update quantity, clear, and session persistence.
    """

    @classmethod
    def setUpTestData(cls):
        cls.producer = User.objects.create_user(
            username='cartproducer', password='testpass123',
            email='cp@test.local', role='producer',
        )
        cls.product_a = Product.objects.create(
            name='Cart Product A',
            description='x', category='vegetables',
            price=Decimal('5.00'), stock_quantity=10,
            producer=cls.producer, is_available=True,
        )
        cls.product_b = Product.objects.create(
            name='Cart Product B',
            description='y', category='fruit',
            price=Decimal('3.00'), stock_quantity=20,
            producer=cls.producer, is_available=True,
        )

    def setUp(self):
        # Each test gets a fresh request with empty session
        self.factory = RequestFactory()
        self.request = self.factory.get('/')
        # RequestFactory doesn't include session middleware — attach manually
        from django.contrib.sessions.backends.db import SessionStore
        self.request.session = SessionStore()

    def test_new_cart_is_empty(self):
        """Cart starts empty for a new session"""
        cart = Cart(self.request)
        self.assertEqual(cart.cart, {})

    def test_add_single_product(self):
        """Adding a product stores it with the given quantity"""
        cart = Cart(self.request)
        cart.add(self.product_a.id, quantity=3)
        self.assertEqual(cart.cart[str(self.product_a.id)], 3)

    def test_add_same_product_twice_accumulates_quantity(self):
        """Re-adding the same product increases the quantity"""
        cart = Cart(self.request)
        cart.add(self.product_a.id, quantity=2)
        cart.add(self.product_a.id, quantity=3)
        self.assertEqual(cart.cart[str(self.product_a.id)], 5)

    def test_add_multiple_products(self):
        """Different products are tracked separately"""
        cart = Cart(self.request)
        cart.add(self.product_a.id, quantity=2)
        cart.add(self.product_b.id, quantity=4)
        self.assertEqual(cart.cart[str(self.product_a.id)], 2)
        self.assertEqual(cart.cart[str(self.product_b.id)], 4)

    def test_update_quantity_replaces_existing(self):
        """Update should set the quantity, not accumulate"""
        cart = Cart(self.request)
        cart.add(self.product_a.id, quantity=2)
        cart.update(self.product_a.id, quantity=10)
        self.assertEqual(cart.cart[str(self.product_a.id)], 10)

    def test_update_to_zero_removes_product(self):
        """Updating quantity to 0 should remove the product entirely"""
        cart = Cart(self.request)
        cart.add(self.product_a.id, quantity=5)
        cart.update(self.product_a.id, quantity=0)
        self.assertNotIn(str(self.product_a.id), cart.cart)

    def test_remove_product(self):
        """Remove deletes the product from the cart"""
        cart = Cart(self.request)
        cart.add(self.product_a.id, quantity=2)
        cart.add(self.product_b.id, quantity=4)
        cart.remove(self.product_a.id)
        self.assertNotIn(str(self.product_a.id), cart.cart)
        self.assertIn(str(self.product_b.id), cart.cart)

    def test_remove_nonexistent_product_does_not_error(self):
        """Removing a product not in cart should fail silently"""
        cart = Cart(self.request)
        cart.remove(self.product_a.id)  # should not raise
        self.assertEqual(cart.cart, {})

    def test_clear_empties_cart(self):
        """Clear removes all products"""
        cart = Cart(self.request)
        cart.add(self.product_a.id, quantity=2)
        cart.add(self.product_b.id, quantity=4)
        cart.clear()
        self.assertEqual(cart.cart, {})

    def test_cart_persists_across_instances_in_same_session(self):
        """Two Cart instances on the same request see the same data"""
        cart1 = Cart(self.request)
        cart1.add(self.product_a.id, quantity=3)

        cart2 = Cart(self.request)  # same session
        self.assertEqual(cart2.cart[str(self.product_a.id)], 3)

class CheckoutResilienceTestCase(TestCase):
    """
    Test suite for checkout robustness when postcodes.io is unreachable.
    Soft-pass behaviour: NETWORK_ERROR should not block checkout, but invalid
    postcodes (API reachable, postcode not real) still reject.
    """

    @classmethod
    def setUpTestData(cls):
        cls.producer = User.objects.create_user(
            username='resilienceproducer', password='testpass123',
            email='rp@test.local', role='producer',
        )
        cls.customer = User.objects.create_user(
            username='resiliencecustomer', password='testpass123',
            email='rc@test.local', role='customer',
        )
        cls.product = Product.objects.create(
            name='Test Product',
            description='x', category='vegetables',
            price=Decimal('5.00'), stock_quantity=10,
            producer=cls.producer, is_available=True,
        )

    def _add_to_cart_and_login(self):
        self.client.login(username='resiliencecustomer', password='testpass123')
        # Add product via the cart endpoint to populate session
        self.client.post(
            reverse('add_to_cart', args=[self.product.id]),
            data={'quantity': 1},
        )

    @patch('orders.views.PostcodesService')
    def test_checkout_proceeds_when_postcodes_api_unreachable(self, mock_service_class):
        """NETWORK_ERROR from postcodes.io should not block checkout"""
        from services.os_places_service import PostcodesService as RealService
        
        mock_service = mock_service_class.return_value
        mock_service.lookup_postcode.return_value = RealService.NETWORK_ERROR
        # NETWORK_ERROR sentinel must match the real one for the comparison
        mock_service_class.NETWORK_ERROR = RealService.NETWORK_ERROR
        
        self._add_to_cart_and_login()
        
        valid_date = timezone.now().date() + timedelta(days=3)
        response = self.client.post(reverse('checkout'), data={
            'postcode': 'BS1 1AB',
            'delivery_address': '23 High Street, Bristol',
            'delivery_date': valid_date,
        })
        
        # Should redirect to Stripe (or wherever payment goes), not re-render the form
        self.assertNotEqual(response.status_code, 200, 
            "Form re-rendered — checkout was blocked when API was unreachable")
        # If a redirect, it shouldn't be back to checkout
        if response.status_code == 302:
            self.assertNotIn('/checkout/', response.url)

    @patch('orders.views.PostcodesService')
    def test_checkout_rejects_invalid_postcode_when_api_works(self, mock_service_class):
        """If API is reachable but postcode is invalid, form should re-render with error"""
        mock_service = mock_service_class.return_value
        mock_service.lookup_postcode.return_value = None  # API said: not a real postcode
        
        self._add_to_cart_and_login()
        
        valid_date = timezone.now().date() + timedelta(days=3)
        response = self.client.post(reverse('checkout'), data={
            'postcode': 'XX99 9XX',
            'delivery_address': '23 High Street, Bristol',
            'delivery_date': valid_date,
        })
        
        # Form re-renders with error
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Invalid postcode')


class CommunityGroupTest(TestCase):
    """TC-017 — community group role + delivery_instructions on checkout."""

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.producer = User.objects.create_user(
            username='cgproducer', email='cgp@test.local',
            password='testpass123', role='producer',
        )
        # ProducerProfile is auto-created by signal; populate the business name
        from producers.models import ProducerProfile
        profile, _ = ProducerProfile.objects.get_or_create(user=cls.producer)
        profile.business_name = 'Test Producer Farm'
        profile.contact_email = 'farm@test.local'
        profile.save()
        cls.product = Product.objects.create(
            producer=cls.producer, name='Bulk Veg Box',
            description='Wholesale veg', category='vegetables',
            price=Decimal('15.00'), stock_quantity=50, is_available=True,
        )

    def test_community_group_role_can_register(self):
        """POST register with role=community_group → user.role='community_group'."""
        User = get_user_model()
        response = self.client.post(reverse('accounts:register'), data={
            'username': 'kitchencg',
            'email': 'kitchencg@test.local',
            'role': 'community_group',
            'password1': 'TestPass123!',
            'password2': 'TestPass123!',
        })
        self.assertEqual(response.status_code, 302)
        user = User.objects.get(username='kitchencg')
        self.assertEqual(user.role, 'community_group')
        self.assertTrue(user.is_buyer)

    @patch('orders.views.stripe.checkout.Session.create')
    @patch('orders.views.PostcodesService')
    def test_delivery_instructions_saved_on_checkout(self, mock_postcodes_class, mock_stripe_create):
        """POST checkout with delivery_instructions → order.delivery_instructions saved."""
        User = get_user_model()
        cg = User.objects.create_user(
            username='kitchen2', email='k2@test.local',
            password='testpass123', role='community_group',
        )
        # Mock postcode lookup to succeed
        mock_postcodes = mock_postcodes_class.return_value
        mock_postcodes.lookup_postcode.return_value = {
            'address': '12 High Street', 'town': 'Bristol',
            'postcode': 'BS1 1AB', 'latitude': 51.45, 'longitude': -2.6,
        }
        # Mock Stripe session create
        mock_stripe_create.return_value = _FakeStripeSession({
            'id': 'sess_cg_1',
            'url': 'https://stripe.example/session/sess_cg_1',
        })

        self.client.login(username='kitchen2', password='testpass123')
        self.client.post(reverse('add_to_cart', args=[self.product.id]), data={'quantity': 2})

        response = self.client.post(reverse('checkout'), data={
            'postcode': 'BS1 1AB',
            'delivery_address': '12 High Street',
            'delivery_date': timezone.now().date() + timedelta(days=3),
            'delivery_instructions': 'Delivery to kitchen — ask for chef.',
        })
        self.assertEqual(response.status_code, 302)  # redirect to Stripe URL
        order = Order.objects.filter(customer=cg).order_by('-id').first()
        self.assertIsNotNone(order)
        self.assertEqual(order.delivery_instructions, 'Delivery to kitchen — ask for chef.')

    def test_order_confirmation_shows_producer_contacts(self):
        """assertContains(confirmation_response, producer_profile.business_name)."""
        User = get_user_model()
        cg = User.objects.create_user(
            username='kitchen3', email='k3@test.local',
            password='testpass123', role='community_group',
        )
        order = Order.objects.create(
            customer=cg,
            total=Decimal('30.00'),
            status='confirmed',
            delivery_date=timezone.now().date() + timedelta(days=3),
            delivery_address='12 High Street, Bristol, BS1 1AB',
            delivery_instructions='Leave at side gate.',
        )
        OrderItem.objects.create(
            order=order, product=self.product, quantity=2, price=Decimal('15.00')
        )

        self.client.login(username='kitchen3', password='testpass123')
        response = self.client.get(reverse('order_confirmation', args=[order.id]))
        self.assertEqual(response.status_code, 200)
        # Per the doc: confirmation must contain producer's business_name
        self.assertContains(response, 'Test Producer Farm')
        # And our delivery_instructions also surfaces
        self.assertContains(response, 'Leave at side gate.')


class RecurringOrderTest(TestCase):
    """TC-018 — recurring orders: save, generate, edit-instance-doesnt-affect-template."""

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.producer = User.objects.create_user(
            username='roproducer', email='rop@test.local',
            password='testpass123', role='producer',
        )
        cls.customer = User.objects.create_user(
            username='rocustomer', email='roc@test.local',
            password='testpass123', role='customer',
        )
        cls.product = Product.objects.create(
            producer=cls.producer, name='Carrots',
            description='Fresh', category='vegetables',
            price=Decimal('5.00'), stock_quantity=100, is_available=True,
        )

    def _make_template(self, quantity=2):
        ro = RecurringOrder.objects.create(
            customer=self.customer,
            name='Weekly box',
            recurrence_day=0,  # Monday
            delivery_day=2,    # Wednesday
            delivery_address='12 High Street, Bristol',
            delivery_instructions='',
        )
        RecurringOrderItem.objects.create(
            recurring_order=ro, product=self.product, quantity=quantity,
        )
        return ro

    def test_customer_can_create_recurring_order(self):
        """POST save_cart_as_recurring → RecurringOrder created in DB."""
        self.client.login(username='rocustomer', password='testpass123')
        # Seed cart
        session = self.client.session
        session['cart'] = {str(self.product.id): 3}
        session.save()

        response = self.client.post(reverse('save_cart_as_recurring'), data={
            'name': 'My weekly box',
            'recurrence_day': 0,
            'delivery_day': 2,
            'delivery_address': '12 High Street, Bristol',
            'delivery_instructions': '',
        })
        self.assertEqual(response.status_code, 302)
        ro = RecurringOrder.objects.filter(customer=self.customer).first()
        self.assertIsNotNone(ro)
        self.assertEqual(ro.name, 'My weekly box')
        self.assertEqual(ro.items.count(), 1)
        self.assertEqual(ro.items.first().quantity, 3)

    def test_generate_command_creates_order_from_recurring(self):
        """Call generate_recurring_orders → new Order created matching template items."""
        ro = self._make_template(quantity=4)
        before = Order.objects.filter(customer=self.customer).count()
        out = StringIO()
        call_command('generate_recurring_orders', '--all', stdout=out)
        after = Order.objects.filter(customer=self.customer).count()
        self.assertEqual(after, before + 1)
        new_order = Order.objects.filter(customer=self.customer).order_by('-id').first()
        self.assertEqual(new_order.status, 'pending')
        self.assertEqual(new_order.items.count(), 1)
        self.assertEqual(new_order.items.first().quantity, 4)
        ro.refresh_from_db()
        self.assertIsNotNone(ro.last_generated_at)

    def test_modifying_instance_does_not_affect_template(self):
        """Edit generated Order quantity → RecurringOrderItem quantity unchanged."""
        ro = self._make_template(quantity=2)
        original_template_qty = ro.items.first().quantity
        call_command('generate_recurring_orders', '--all', stdout=StringIO())
        new_order = Order.objects.filter(customer=self.customer).order_by('-id').first()

        # Modify the generated Order's item
        order_item = new_order.items.first()
        order_item.quantity = 99
        order_item.save()

        # Template should be untouched
        ro.refresh_from_db()
        template_item = ro.items.first()
        self.assertEqual(template_item.quantity, original_template_qty)
        self.assertNotEqual(template_item.quantity, order_item.quantity)


class MultiProducerCheckoutTest(TestCase):
    """TC-008 — multi-vendor checkout creates a single Order with items from each producer."""

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.customer = User.objects.create_user(
            username='mpcust', email='mpc@test.local',
            password='testpass123', role='customer',
        )
        cls.producer1 = User.objects.create_user(
            username='mpprod1', email='mpp1@test.local',
            password='testpass123', role='producer',
        )
        cls.producer2 = User.objects.create_user(
            username='mpprod2', email='mpp2@test.local',
            password='testpass123', role='producer',
        )
        cls.product1 = Product.objects.create(
            producer=cls.producer1, name='MP Carrots',
            description='F', category='vegetables',
            price=Decimal('5.00'), stock_quantity=20, is_available=True,
        )
        cls.product2 = Product.objects.create(
            producer=cls.producer2, name='MP Milk',
            description='F', category='dairy',
            price=Decimal('3.00'), stock_quantity=20, is_available=True,
        )

    @patch('orders.views.stripe.checkout.Session.create')
    @patch('orders.views.PostcodesService')
    def test_multi_producer_cart_creates_single_order(self, mock_postcodes_class, mock_stripe_create):
        """Cart with products from 2 producers → 1 Order, 2+ OrderItems after checkout."""
        mock_postcodes = mock_postcodes_class.return_value
        mock_postcodes.lookup_postcode.return_value = {
            'address': '12 High Street', 'town': 'Bristol',
            'postcode': 'BS1 1AB', 'latitude': 51.45, 'longitude': -2.6,
        }
        mock_stripe_create.return_value = _FakeStripeSession({
            'id': 'sess_mp_1',
            'url': 'https://stripe.example/sess_mp_1',
        })

        self.client.login(username='mpcust', password='testpass123')
        self.client.post(reverse('add_to_cart', args=[self.product1.id]), data={'quantity': 1})
        self.client.post(reverse('add_to_cart', args=[self.product2.id]), data={'quantity': 1})

        response = self.client.post(reverse('checkout'), data={
            'postcode': 'BS1 1AB',
            'delivery_address': '12 High Street',
            'delivery_date': timezone.now().date() + timedelta(days=3),
        })
        self.assertEqual(response.status_code, 302)

        orders = Order.objects.filter(customer=self.customer)
        self.assertEqual(orders.count(), 1)
        order = orders.first()
        self.assertGreaterEqual(order.items.count(), 2)
        # Items must span both producers
        producer_ids = set(item.product.producer_id for item in order.items.all())
        self.assertEqual(len(producer_ids), 2)

    def test_each_producer_sees_only_own_items(self):
        """Producer 1 dashboard only shows items from their products, not Producer 2's."""
        order = Order.objects.create(
            customer=self.customer, total=Decimal('8.00'),
            status='confirmed',
            delivery_date=timezone.now().date() + timedelta(days=3),
            delivery_address='12 High St, Bristol, BS1 1AB',
        )
        OrderItem.objects.create(order=order, product=self.product1, quantity=1, price=Decimal('5.00'))
        OrderItem.objects.create(order=order, product=self.product2, quantity=1, price=Decimal('3.00'))

        self.client.login(username='mpprod1', password='testpass123')
        response = self.client.get(reverse('producer_dashboard'))
        self.assertEqual(response.status_code, 200)
        orders_in_context = list(response.context['orders'])
        self.assertEqual(len(orders_in_context), 1)
        producer_items = orders_in_context[0].producer_items
        self.assertEqual(len(producer_items), 1)
        self.assertEqual(producer_items[0].product_id, self.product1.id)


class ProducerOrderViewTest(TestCase):
    """TC-009 — producer dashboard scoping (own items only) + customer details."""

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.customer = User.objects.create_user(
            username='pocust', email='poc@test.local',
            password='testpass123', role='customer',
        )
        cls.producer1 = User.objects.create_user(
            username='poprod1', email='pop1@test.local',
            password='testpass123', role='producer',
        )
        cls.producer2 = User.objects.create_user(
            username='poprod2', email='pop2@test.local',
            password='testpass123', role='producer',
        )
        cls.product1 = Product.objects.create(
            producer=cls.producer1, name='PO Apples',
            description='F', category='fruit',
            price=Decimal('4.00'), stock_quantity=20, is_available=True,
        )
        cls.product2 = Product.objects.create(
            producer=cls.producer2, name='PO Cheese',
            description='F', category='dairy',
            price=Decimal('6.00'), stock_quantity=20, is_available=True,
        )

    def _make_dual_producer_order(self):
        order = Order.objects.create(
            customer=self.customer, total=Decimal('10.00'),
            status='confirmed',
            delivery_date=timezone.now().date() + timedelta(days=3),
            delivery_address='42 Customer Road, Bristol, BS1 2CD',
        )
        OrderItem.objects.create(order=order, product=self.product1, quantity=1, price=Decimal('4.00'))
        OrderItem.objects.create(order=order, product=self.product2, quantity=1, price=Decimal('6.00'))
        return order

    def test_producer_sees_only_own_order_items(self):
        """Producer dashboard context contains only items from their products."""
        self._make_dual_producer_order()
        self.client.login(username='poprod1', password='testpass123')
        response = self.client.get(reverse('producer_dashboard'))
        orders_in_context = list(response.context['orders'])
        self.assertEqual(len(orders_in_context), 1)
        for item in orders_in_context[0].producer_items:
            self.assertEqual(item.product.producer_id, self.producer1.id)

    def test_producer_cannot_see_other_producer_items(self):
        """Items from another producer's products absent from dashboard context."""
        self._make_dual_producer_order()
        self.client.login(username='poprod1', password='testpass123')
        response = self.client.get(reverse('producer_dashboard'))
        orders_in_context = list(response.context['orders'])
        item_product_ids = [item.product_id for item in orders_in_context[0].producer_items]
        self.assertIn(self.product1.id, item_product_ids)
        self.assertNotIn(self.product2.id, item_product_ids)

    def test_orders_show_customer_details(self):
        """Order in dashboard context has customer username and delivery_address."""
        self._make_dual_producer_order()
        self.client.login(username='poprod1', password='testpass123')
        response = self.client.get(reverse('producer_dashboard'))
        self.assertContains(response, self.customer.username)
        self.assertContains(response, '42 Customer Road')


class OrderStatusTest(TestCase):
    """TC-010 — producer updates order status through lifecycle.

    NB: PR #16 moved per-producer tracking onto Delivery rows.
    test_ship_order_sets_dispatched_and_tracking asserts the new behaviour
    (Delivery.tracking_number + Delivery.producer_ready_at) instead of the
    legacy Order.status='dispatched' + Order.tracking_number.
    """

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.customer = User.objects.create_user(
            username='oscust', email='osc@test.local',
            password='testpass123', role='customer',
        )
        cls.producer = User.objects.create_user(
            username='osprod', email='osp@test.local',
            password='testpass123', role='producer',
        )
        cls.product = Product.objects.create(
            producer=cls.producer, name='OS Veg',
            description='F', category='vegetables',
            price=Decimal('5.00'), stock_quantity=50, is_available=True,
        )

    def _make_confirmed_order(self, packed=False):
        """Create order + item + flip to confirmed so the post_save signal makes Delivery."""
        order = Order.objects.create(
            customer=self.customer, total=Decimal('5.00'),
            status='pending',
            delivery_date=timezone.now().date() + timedelta(days=3),
            delivery_address='1 OS Lane, Bristol, BS1 3EF',
        )
        item = OrderItem.objects.create(
            order=order, product=self.product, quantity=1,
            price=Decimal('5.00'), is_packed=packed,
        )
        order.status = 'confirmed'
        order.save()
        return order, item

    def test_toggle_item_packed_flips_boolean(self):
        """POST toggle_item_packed/pk/ → item.is_packed flips."""
        _, item = self._make_confirmed_order(packed=False)
        self.client.login(username='osprod', password='testpass123')

        self.client.post(reverse('toggle_item_packed', args=[item.id]))
        item.refresh_from_db()
        self.assertTrue(item.is_packed)

        self.client.post(reverse('toggle_item_packed', args=[item.id]))
        item.refresh_from_db()
        self.assertFalse(item.is_packed)

    def test_mark_order_ready_sets_processing(self):
        """POST mark_order_ready/pk/ with all items packed → order.status='processing'."""
        order, _ = self._make_confirmed_order(packed=True)
        self.client.login(username='osprod', password='testpass123')

        self.client.post(reverse('mark_order_ready', args=[order.id]))
        order.refresh_from_db()
        self.assertEqual(order.status, 'processing')

    def test_ship_order_sets_dispatched_and_tracking(self):
        """POST ship_order/pk/ → producer's Delivery has tracking_number + producer_ready_at.

        Post-PR-#16 the per-producer tracking lives on Delivery (not Order).
        Method name kept to match the testing guide; assertions reflect reality.
        """
        order, _ = self._make_confirmed_order(packed=True)
        self.client.login(username='osprod', password='testpass123')

        self.client.post(reverse('ship_order', args=[order.id]))
        delivery = Delivery.objects.get(order=order, producer=self.producer)
        self.assertIsNotNone(delivery.producer_ready_at)
        self.assertTrue(delivery.tracking_number.startswith('DESD-'))
        self.assertEqual(len(delivery.tracking_number), len('DESD-') + 10)

    def test_ship_order_sends_dispatch_email(self):
        """POST ship_order/pk/ → email sent to customer."""
        from django.core import mail
        mail.outbox = []
        order, _ = self._make_confirmed_order(packed=True)
        self.client.login(username='osprod', password='testpass123')

        self.client.post(reverse('ship_order', args=[order.id]))
        self.assertGreaterEqual(len(mail.outbox), 1)
        recipients = [r for m in mail.outbox for r in m.to]
        self.assertIn(self.customer.email, recipients)
class ReorderTestCase(TestCase):
    """
    Test suite for TC-021: customer reorder function.
    Reorder copies items from a past order back into the cart, handling
    unavailable and out-of-stock products gracefully.
    """

    @classmethod
    def setUpTestData(cls):
        cls.producer = User.objects.create_user(
            username='reorderproducer', password='testpass123',
            email='rp@test.local', role='producer',
        )
        cls.customer = User.objects.create_user(
            username='reordercustomer', password='testpass123',
            email='rc@test.local', role='customer',
        )
        cls.product_available = Product.objects.create(
            name='Available Product',
            description='x', category='vegetables',
            price=Decimal('5.00'), stock_quantity=10,
            producer=cls.producer, is_available=True,
        )
        cls.product_unavailable = Product.objects.create(
            name='Unavailable Product',
            description='x', category='vegetables',
            price=Decimal('5.00'), stock_quantity=10,
            producer=cls.producer, is_available=False,
        )
        cls.product_out_of_stock = Product.objects.create(
            name='Out Of Stock Product',
            description='x', category='vegetables',
            price=Decimal('5.00'), stock_quantity=0,
            producer=cls.producer, is_available=True,
        )

    def _make_order_with_items(self, items):
        """items: list of (product, quantity) tuples"""
        order = Order.objects.create(
            customer=self.customer,
            total=Decimal('5.00'),
            status='delivered',
            delivery_date=timezone.now().date() + timedelta(days=3),
            delivery_address='Bristol',
        )
        for product, qty in items:
            OrderItem.objects.create(
                order=order, product=product,
                quantity=qty, price=product.price,
            )
        return order

    def test_reorder_adds_available_items_to_cart(self):
        """All available, in-stock items should land in cart"""
        order = self._make_order_with_items([(self.product_available, 3)])
        self.client.login(username='reordercustomer', password='testpass123')

        self.client.post(reverse('reorder', args=[order.id]))

        # Need to fetch session to see cart
        session = self.client.session
        cart = session.get('cart', {})
        self.assertEqual(cart.get(str(self.product_available.id)), 3)

    def test_reorder_skips_unavailable_products(self):
        """Products marked is_available=False should not be added"""
        order = self._make_order_with_items([
            (self.product_available, 2),
            (self.product_unavailable, 1),
        ])
        self.client.login(username='reordercustomer', password='testpass123')

        self.client.post(reverse('reorder', args=[order.id]))

        cart = self.client.session.get('cart', {})
        self.assertIn(str(self.product_available.id), cart)
        self.assertNotIn(str(self.product_unavailable.id), cart)

    def test_reorder_skips_out_of_stock_products(self):
        """Products with stock_quantity=0 should not be added"""
        order = self._make_order_with_items([
            (self.product_out_of_stock, 5),
        ])
        self.client.login(username='reordercustomer', password='testpass123')

        self.client.post(reverse('reorder', args=[order.id]))

        cart = self.client.session.get('cart', {})
        self.assertNotIn(str(self.product_out_of_stock.id), cart)

    def test_reorder_caps_quantity_at_current_stock(self):
        """If original order qty exceeds current stock, cap at stock"""
        order = self._make_order_with_items([(self.product_available, 50)])  # only 10 in stock
        self.client.login(username='reordercustomer', password='testpass123')

        self.client.post(reverse('reorder', args=[order.id]))

        cart = self.client.session.get('cart', {})
        self.assertEqual(cart.get(str(self.product_available.id)), 10)

    def test_reorder_blocked_for_other_customers_orders(self):
        """Customer can't reorder another customer's order"""
        other_customer = User.objects.create_user(
            username='other', password='testpass123',
            email='other@test.local', role='customer',
        )
        order = Order.objects.create(
            customer=other_customer,
            total=Decimal('5.00'),
            status='delivered',
            delivery_date=timezone.now().date() + timedelta(days=3),
            delivery_address='Bristol',
        )
        OrderItem.objects.create(
            order=order, product=self.product_available,
            quantity=3, price=self.product_available.price,
        )
        self.client.login(username='reordercustomer', password='testpass123')

        response = self.client.post(reverse('reorder', args=[order.id]))

        cart = self.client.session.get('cart', {})
        self.assertEqual(cart, {})  # nothing added — order didn't belong to this customer
        self.assertEqual(response.status_code, 404)

    def test_reorder_blocked_for_producer_role(self):
        """Producer can't use reorder endpoint"""
        order = self._make_order_with_items([(self.product_available, 2)])
        self.client.login(username='reorderproducer', password='testpass123')

        self.client.post(reverse('reorder', args=[order.id]))

        cart = self.client.session.get('cart', {})
        self.assertEqual(cart, {})
