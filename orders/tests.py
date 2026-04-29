from decimal import Decimal
from datetime import timedelta
from unittest.mock import patch
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from products.models import Product
from .forms import CheckoutForm
from .models import Order, OrderItem, Payment
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