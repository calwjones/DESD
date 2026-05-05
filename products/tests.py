from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django.urls import reverse

from products.models import Product

from django.utils import timezone
from datetime import timedelta

from products.models import Review
from products.forms import ReviewForm
from orders.models import Order, OrderItem

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

class ReviewModelTestCase(TestCase):
    """
    Test suite for TC-024: Review model — rating constraints,
    unique-per-customer-per-product, and field requirements.
    """

    @classmethod
    def setUpTestData(cls):
        cls.producer = User.objects.create_user(
            username='reviewproducer', password='testpass123',
            email='rp@test.local', role='producer',
        )
        cls.customer = User.objects.create_user(
            username='reviewcustomer', password='testpass123',
            email='rc@test.local', role='customer',
        )
        cls.product = Product.objects.create(
            name='Reviewable Product',
            description='x', category='vegetables',
            price=5.00, stock_quantity=10,
            producer=cls.producer, is_available=True,
        )

    def test_review_can_be_created_with_valid_data(self):
        """Customer creates a review with rating, title, body"""
        review = Review.objects.create(
            product=self.product,
            customer=self.customer,
            rating=5,
            title='Great',
            body='Really enjoyed it.',
            is_verified_purchase=True,
        )
        self.assertEqual(review.rating, 5)
        self.assertTrue(review.is_verified_purchase)

    def test_one_review_per_customer_per_product(self):
        """unique_together prevents duplicate reviews for same product+customer"""
        Review.objects.create(
            product=self.product, customer=self.customer,
            rating=5, title='First', body='ok',
        )
        with self.assertRaises(Exception):  # IntegrityError
            Review.objects.create(
                product=self.product, customer=self.customer,
                rating=4, title='Second', body='also ok',
            )

    def test_review_can_be_blank_title_and_body(self):
        """Customer can leave a rating-only review"""
        review = Review.objects.create(
            product=self.product, customer=self.customer,
            rating=4, title='', body='',
        )
        self.assertEqual(review.rating, 4)
        self.assertEqual(review.title, '')


class ReviewFormTestCase(TestCase):
    """
    Test suite for TC-024: form validation — rating range,
    title-and-body all-or-nothing rule.
    """

    def test_form_accepts_rating_only(self):
        """Star-only review (no title, no body) should validate"""
        form = ReviewForm(data={'rating': 5, 'title': '', 'body': ''})
        self.assertTrue(form.is_valid(), form.errors)

    def test_form_accepts_full_review(self):
        """Rating + title + body should validate"""
        form = ReviewForm(data={
            'rating': 4, 'title': 'Good', 'body': 'Properly tasty.'
        })
        self.assertTrue(form.is_valid(), form.errors)

    def test_form_rejects_title_without_body(self):
        """Title set, body empty: should fail with non-field error"""
        form = ReviewForm(data={'rating': 4, 'title': 'Hmm', 'body': ''})
        self.assertFalse(form.is_valid())
        self.assertIn('both', str(form.non_field_errors()).lower())

    def test_form_rejects_body_without_title(self):
        """Body set, title empty: should fail with non-field error"""
        form = ReviewForm(data={'rating': 4, 'title': '', 'body': 'Decent'})
        self.assertFalse(form.is_valid())
        self.assertIn('both', str(form.non_field_errors()).lower())

    def test_form_rejects_invalid_rating(self):
        """Rating outside 1-5 should fail"""
        form = ReviewForm(data={'rating': 6, 'title': '', 'body': ''})
        self.assertFalse(form.is_valid())

    def test_form_strips_whitespace_only_input_to_empty(self):
        """Title or body of just spaces should be treated as empty"""
        form = ReviewForm(data={
            'rating': 5, 'title': '   ', 'body': '   '
        })
        self.assertTrue(form.is_valid(), form.errors)
        # Both end up stripped to empty, which is allowed
        self.assertEqual(form.cleaned_data['title'], '')
        self.assertEqual(form.cleaned_data['body'], '')


class ReviewViewTestCase(TestCase):
    """
    Test suite for TC-024: write_review view permissions and behaviour.
    Only customers with delivered orders can review; one review per product.
    """

    @classmethod
    def setUpTestData(cls):
        cls.producer = User.objects.create_user(
            username='vp', password='testpass123',
            email='vp@test.local', role='producer',
        )
        cls.customer = User.objects.create_user(
            username='vc', password='testpass123',
            email='vc@test.local', role='customer',
        )
        cls.other_customer = User.objects.create_user(
            username='vc2', password='testpass123',
            email='vc2@test.local', role='customer',
        )
        cls.product = Product.objects.create(
            name='View Test Product',
            description='x', category='vegetables',
            price=5.00, stock_quantity=10,
            producer=cls.producer, is_available=True,
        )

    def _make_order(self, customer, status='delivered'):
        order = Order.objects.create(
            customer=customer,
            total=5.00,
            status=status,
            delivery_date=timezone.now().date() + timedelta(days=3),
            delivery_address='Bristol',
        )
        OrderItem.objects.create(
            order=order, product=self.product,
            quantity=1, price=5.00,
        )
        return order

    def test_customer_with_delivered_order_can_review(self):
        """Customer who has received the product can post a review"""
        self._make_order(self.customer, status='delivered')
        self.client.login(username='vc', password='testpass123')

        response = self.client.post(
            reverse('products:write_review', args=[self.product.id]),
            data={'rating': 5, 'title': 'Great', 'body': 'Loved it'},
        )
        self.assertEqual(Review.objects.filter(product=self.product, customer=self.customer).count(), 1)

    def test_customer_without_delivered_order_blocked(self):
        """Customer with no delivered order for this product cannot review"""
        self.client.login(username='vc', password='testpass123')

        self.client.post(
            reverse('products:write_review', args=[self.product.id]),
            data={'rating': 5, 'title': 'Great', 'body': 'Loved it'},
        )
        self.assertEqual(Review.objects.filter(product=self.product, customer=self.customer).count(), 0)

    def test_customer_with_only_pending_order_blocked(self):
        """Order status other than delivered should not allow review"""
        self._make_order(self.customer, status='pending')
        self.client.login(username='vc', password='testpass123')

        self.client.post(
            reverse('products:write_review', args=[self.product.id]),
            data={'rating': 5, 'title': 'Great', 'body': 'Loved it'},
        )
        self.assertEqual(Review.objects.filter(product=self.product, customer=self.customer).count(), 0)

    def test_producer_cannot_post_review(self):
        """Only customers can write reviews"""
        self.client.login(username='vp', password='testpass123')

        self.client.post(
            reverse('products:write_review', args=[self.product.id]),
            data={'rating': 5, 'title': 'My own product', 'body': 'rigged'},
        )
        self.assertEqual(Review.objects.filter(product=self.product).count(), 0)

    def test_customer_cannot_review_twice(self):
        """Second review attempt by same customer should be rejected"""
        self._make_order(self.customer, status='delivered')
        Review.objects.create(
            product=self.product, customer=self.customer,
            rating=5, title='First', body='ok',
        )
        self.client.login(username='vc', password='testpass123')

        self.client.post(
            reverse('products:write_review', args=[self.product.id]),
            data={'rating': 1, 'title': 'Second', 'body': 'changed mind'},
        )
        # Still only one review
        self.assertEqual(Review.objects.filter(product=self.product, customer=self.customer).count(), 1)
        # Original review unchanged
        review = Review.objects.get(product=self.product, customer=self.customer)
        self.assertEqual(review.rating, 5)
        self.assertEqual(review.title, 'First')