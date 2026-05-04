from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django.urls import reverse

from products.models import Product

User = get_user_model()


class StockThresholdTestCase(TestCase):
    """
    Test suite for TC-023: Low stock notifications.
    Producer can set a threshold; system alerts via dashboard badge and email
    when stock drops to or below threshold.
    """

    @classmethod
    def setUpTestData(cls):
        cls.producer = User.objects.create_user(
            username='testproducer',
            password='testpass123',
            email='producer@test.local',
            role='producer',
        )

    def _make_product(self, **overrides):
        defaults = {
            'name': 'Test Product',
            'description': 'For testing',
            'category': 'vegetables',
            'price': 5.00,
            'stock_quantity': 50,
            'producer': self.producer,
            'is_available': True,
        }
        defaults.update(overrides)
        return Product.objects.create(**defaults)

    def test_threshold_zero_disables_alert(self):
        """is_low_stock returns False when threshold is 0 regardless of stock"""
        product = self._make_product(stock_quantity=0, stock_threshold=0)
        self.assertFalse(product.is_low_stock)

    def test_stock_above_threshold_no_alert(self):
        """is_low_stock returns False when stock exceeds threshold"""
        product = self._make_product(stock_quantity=20, stock_threshold=10)
        self.assertFalse(product.is_low_stock)

    def test_stock_at_threshold_triggers_alert(self):
        """is_low_stock returns True when stock equals threshold"""
        product = self._make_product(stock_quantity=10, stock_threshold=10)
        self.assertTrue(product.is_low_stock)

    def test_stock_below_threshold_triggers_alert(self):
        """is_low_stock returns True when stock drops below threshold"""
        product = self._make_product(stock_quantity=5, stock_threshold=10)
        self.assertTrue(product.is_low_stock)


class LowStockEmailTestCase(TestCase):
    """
    Test suite for TC-023: opt-in email alerts on threshold crossing.
    Email fires once on first crossing and again after recovery + re-drop;
    never on subsequent saves while still low.
    """

    @classmethod
    def setUpTestData(cls):
        cls.producer = User.objects.create_user(
            username='emailproducer',
            password='testpass123',
            email='producer@test.local',
            role='producer',
        )

    def _make_product(self, **overrides):
        defaults = {
            'name': 'Email Test Product',
            'description': 'For email testing',
            'category': 'vegetables',
            'price': 5.00,
            'stock_quantity': 50,
            'producer': self.producer,
            'is_available': True,
            'stock_threshold': 10,
            'low_stock_email_alerts': True,
        }
        defaults.update(overrides)
        return Product.objects.create(**defaults)

    def test_email_fires_when_stock_drops_to_threshold(self):
        """Crossing from above threshold to at-or-below should send one email"""
        product = self._make_product(stock_quantity=50)
        mail.outbox = []  # clear any setUp emails

        product.stock_quantity = 5
        product.save()

        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('Low Stock Alert', mail.outbox[0].subject)

    def test_email_does_not_fire_when_alerts_disabled(self):
        """Disabled email alerts should suppress notifications even on drop"""
        product = self._make_product(low_stock_email_alerts=False, stock_quantity=50)
        mail.outbox = []

        product.stock_quantity = 5
        product.save()

        self.assertEqual(len(mail.outbox), 0)

    def test_email_does_not_re_fire_on_subsequent_saves_while_low(self):
        """Saving again while still low must not re-send the email"""
        product = self._make_product(stock_quantity=5)  # already low at create
        mail.outbox = []

        product.save()
        product.save()

        self.assertEqual(len(mail.outbox), 0)

    def test_alert_resets_on_recovery(self):
        """Stock recovering above threshold should reset the alerted flag"""
        product = self._make_product(stock_quantity=5)  # low at create, fires email
        product.refresh_from_db()
        self.assertTrue(product.low_stock_alerted)

        product.stock_quantity = 50
        product.save()
        product.refresh_from_db()

        self.assertFalse(product.low_stock_alerted)

    def test_email_re_fires_after_recovery_and_re_drop(self):
        """Full lifecycle: drop fires email, recovery resets, re-drop fires again"""
        product = self._make_product(stock_quantity=5)  # initial drop fires
        mail.outbox = []

        product.stock_quantity = 50
        product.save()  # recovery, no email
        self.assertEqual(len(mail.outbox), 0)

        product.stock_quantity = 5
        product.save()  # re-drop, fires again
        self.assertEqual(len(mail.outbox), 1)


class LowStockDashboardTestCase(TestCase):
    """
    Test suite for TC-023: producer dashboard shows low-stock alert banner
    and per-product badge.
    """

    @classmethod
    def setUpTestData(cls):
        cls.producer = User.objects.create_user(
            username='dashproducer',
            password='testpass123',
            email='dash@test.local',
            role='producer',
        )

    def test_low_stock_banner_appears_when_product_below_threshold(self):
        """Dashboard banner should list low-stock products"""
        Product.objects.create(
            name='Low Item', description='x', category='vegetables',
            price=1.00, stock_quantity=2, stock_threshold=10,
            producer=self.producer, is_available=True,
        )

        self.client.login(username='dashproducer', password='testpass123')
        response = self.client.get(reverse('producer_dashboard'))

        self.assertContains(response, 'Low stock alert')
        self.assertContains(response, 'Low Item')

    def test_low_stock_banner_hidden_when_no_low_products(self):
        """Banner should not appear when nothing is below threshold"""
        Product.objects.create(
            name='Healthy Item', description='x', category='vegetables',
            price=1.00, stock_quantity=50, stock_threshold=10,
            producer=self.producer, is_available=True,
        )

        self.client.login(username='dashproducer', password='testpass123')
        response = self.client.get(reverse('producer_dashboard'))

        self.assertNotContains(response, 'Low stock alert')