from datetime import timedelta
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from products.models import Product
from django.core import mail

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


# ======================================================================
# TC-003 — ProductManagementTest
# ======================================================================
class ProductManagementTest(TestCase):
    """TC-003 — producer creates, edits, deletes products; customers blocked."""

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.producer1 = User.objects.create_user(
            username='pmprod1', email='pm1@test.local',
            password='testpass123', role='producer',
        )
        cls.producer2 = User.objects.create_user(
            username='pmprod2', email='pm2@test.local',
            password='testpass123', role='producer',
        )
        cls.customer = User.objects.create_user(
            username='pmcust', email='pmc@test.local',
            password='testpass123', role='customer',
        )

    def _add_product_payload(self, **overrides):
        payload = {
            'name': 'Test Product',
            'description': 'desc',
            'category': 'vegetables',
            'price': '5.00',
            'stock_quantity': 10,
            'stock_threshold': 0,
            'is_available': 'on',
            'enable_ai_grading': '',  # opt out so we don't need to mock the AI
        }
        payload.update(overrides)
        return payload

    def test_producer_can_add_product(self):
        """POST /products/add/ as producer creates Product in DB linked to that producer."""
        self.client.login(username='pmprod1', password='testpass123')
        response = self.client.post(reverse('products:add'), data=self._add_product_payload(name='New Carrots'))
        self.assertEqual(response.status_code, 302)
        product = Product.objects.get(name='New Carrots')
        self.assertEqual(product.producer, self.producer1)

    def test_product_appears_in_marketplace(self):
        """After creation, product name appears in GET /."""
        product = Product.objects.create(
            producer=self.producer1, name='Marketplace Visible Veg',
            description='d', category='vegetables', price=5,
            stock_quantity=5, is_available=True,
        )
        self.client.login(username='pmcust', password='testpass123')
        response = self.client.get(reverse('marketplace'))
        self.assertContains(response, 'Marketplace Visible Veg')

    def test_customer_cannot_add_product(self):
        """POST /products/add/ as customer returns redirect, no product created."""
        self.client.login(username='pmcust', password='testpass123')
        before = Product.objects.count()
        response = self.client.post(reverse('products:add'), data=self._add_product_payload(name='Should Not Exist'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Product.objects.count(), before)
        self.assertFalse(Product.objects.filter(name='Should Not Exist').exists())

    def test_producer_can_edit_own_product(self):
        """POST /products/<pk>/edit/ updates product name in DB."""
        product = Product.objects.create(
            producer=self.producer1, name='Old Name',
            description='d', category='vegetables', price=5,
            stock_quantity=5, is_available=True,
        )
        self.client.login(username='pmprod1', password='testpass123')
        self.client.post(
            reverse('products:edit', args=[product.id]),
            data=self._add_product_payload(name='New Name'),
        )
        product.refresh_from_db()
        self.assertEqual(product.name, 'New Name')

    def test_producer_cannot_edit_other_producers_product(self):
        """POST edit on another producer's product → 404 (not their resource)."""
        product = Product.objects.create(
            producer=self.producer1, name='Owned by 1',
            description='d', category='vegetables', price=5,
            stock_quantity=5, is_available=True,
        )
        self.client.login(username='pmprod2', password='testpass123')
        response = self.client.post(
            reverse('products:edit', args=[product.id]),
            data=self._add_product_payload(name='Hijacked'),
        )
        # 404 (the queryset filters to producer=self.user) — name unchanged
        self.assertEqual(response.status_code, 404)
        product.refresh_from_db()
        self.assertEqual(product.name, 'Owned by 1')

    def test_producer_can_delete_own_product(self):
        """POST /products/<pk>/delete/ removes product from DB."""
        product = Product.objects.create(
            producer=self.producer1, name='Delete Me',
            description='d', category='vegetables', price=5,
            stock_quantity=5, is_available=True,
        )
        self.client.login(username='pmprod1', password='testpass123')
        self.client.post(reverse('products:delete', args=[product.id]))
        self.assertFalse(Product.objects.filter(id=product.id).exists())


# ======================================================================
# TC-011 — InventoryTest
# ======================================================================
class InventoryTest(TestCase):
    """TC-011 — producer updates stock + availability."""

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.producer = User.objects.create_user(
            username='invprod', email='inv@test.local',
            password='testpass123', role='producer',
        )
        cls.customer = User.objects.create_user(
            username='invcust', email='invc@test.local',
            password='testpass123', role='customer',
        )

    def _edit_payload(self, **overrides):
        payload = {
            'name': 'Inv Test',
            'description': 'd',
            'category': 'vegetables',
            'price': '5.00',
            'stock_quantity': 10,
            'stock_threshold': 0,
            'is_available': 'on',
            'enable_ai_grading': '',
        }
        payload.update(overrides)
        return payload

    def test_stock_quantity_updates_correctly(self):
        """POST edit with stock_quantity=35 saves 35 to DB."""
        product = Product.objects.create(
            producer=self.producer, name='Inv Test',
            description='d', category='vegetables', price=5,
            stock_quantity=10, is_available=True,
        )
        self.client.login(username='invprod', password='testpass123')
        self.client.post(
            reverse('products:edit', args=[product.id]),
            data=self._edit_payload(stock_quantity=35),
        )
        product.refresh_from_db()
        self.assertEqual(product.stock_quantity, 35)

    def test_unavailable_product_hidden_from_marketplace(self):
        """Product with is_available=False not in marketplace context."""
        Product.objects.create(
            producer=self.producer, name='Inv Hidden',
            description='d', category='vegetables', price=5,
            stock_quantity=5, is_available=False,
        )
        self.client.login(username='invcust', password='testpass123')
        response = self.client.get(reverse('marketplace'))
        product_names = [p.name for p in response.context['products']]
        self.assertNotIn('Inv Hidden', product_names)

    def test_available_product_visible_in_marketplace(self):
        """Product with is_available=True appears in marketplace context."""
        Product.objects.create(
            producer=self.producer, name='Inv Visible',
            description='d', category='vegetables', price=5,
            stock_quantity=5, is_available=True,
        )
        self.client.login(username='invcust', password='testpass123')
        response = self.client.get(reverse('marketplace'))
        product_names = [p.name for p in response.context['products']]
        self.assertIn('Inv Visible', product_names)

    def test_negative_stock_rejected(self):
        """POST edit with stock_quantity=-1 returns form errors."""
        product = Product.objects.create(
            producer=self.producer, name='Neg Stock',
            description='d', category='vegetables', price=5,
            stock_quantity=10, is_available=True,
        )
        self.client.login(username='invprod', password='testpass123')
        response = self.client.post(
            reverse('products:edit', args=[product.id]),
            data=self._edit_payload(stock_quantity=-1),
        )
        # Form re-renders (200) with errors; product unchanged
        self.assertEqual(response.status_code, 200)
        product.refresh_from_db()
        self.assertEqual(product.stock_quantity, 10)


# ======================================================================
# TC-014 — OrganicFilterTest
# ======================================================================
class OrganicFilterTest(TestCase):
    """TC-014 — organic certification filter on the marketplace."""

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.producer = User.objects.create_user(
            username='ofprod', email='of@test.local',
            password='testpass123', role='producer',
        )
        cls.customer = User.objects.create_user(
            username='ofcust', email='ofc@test.local',
            password='testpass123', role='customer',
        )
        cls.organic = Product.objects.create(
            producer=cls.producer, name='OF Organic Carrots',
            description='d', category='vegetables', price=5,
            stock_quantity=10, is_available=True, is_organic=True,
        )
        cls.non_organic = Product.objects.create(
            producer=cls.producer, name='OF Regular Spuds',
            description='d', category='vegetables', price=4,
            stock_quantity=10, is_available=True, is_organic=False,
        )

    def test_organic_filter_returns_only_organic(self):
        """GET / with organic filter — all products in context have is_organic=True."""
        self.client.login(username='ofcust', password='testpass123')
        # NB: implementation uses `?organic=on` (the doc spec said `organic_only=on`)
        response = self.client.get(reverse('marketplace') + '?organic=on')
        for product in response.context['products']:
            self.assertTrue(product.is_organic)

    def test_non_organic_excluded_from_filter(self):
        """Non-organic product absent from organic filter results."""
        self.client.login(username='ofcust', password='testpass123')
        response = self.client.get(reverse('marketplace') + '?organic=on')
        names = [p.name for p in response.context['products']]
        self.assertIn('OF Organic Carrots', names)
        self.assertNotIn('OF Regular Spuds', names)

    def test_no_filter_returns_all_products(self):
        """GET / with no filter returns both organic and non-organic."""
        self.client.login(username='ofcust', password='testpass123')
        response = self.client.get(reverse('marketplace'))
        names = [p.name for p in response.context['products']]
        self.assertIn('OF Organic Carrots', names)
        self.assertIn('OF Regular Spuds', names)


# ======================================================================
# TC-015 — AllergenTest
# ======================================================================
class AllergenTest(TestCase):
    """TC-015 — allergen warnings displayed on product detail."""

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.producer = User.objects.create_user(
            username='alprod', email='al@test.local',
            password='testpass123', role='producer',
        )
        cls.customer = User.objects.create_user(
            username='alcust', email='alc@test.local',
            password='testpass123', role='customer',
        )

    def test_allergen_info_shown_on_product_detail(self):
        """assertContains(response, allergen_display) on product detail page."""
        product = Product.objects.create(
            producer=self.producer, name='Wheat Loaf',
            description='d', category='bakery', price=3,
            stock_quantity=5, is_available=True,
            allergen_info='gluten,milk',
        )
        self.client.login(username='alcust', password='testpass123')
        response = self.client.get(reverse('products:detail', args=[product.id]))
        # Product.allergen_display renders human-readable names
        self.assertContains(response, 'Gluten')
        self.assertContains(response, 'Milk')

    def test_no_allergens_shows_fallback_message(self):
        """Product with empty allergen_info shows 'No allergens declared' on detail page."""
        product = Product.objects.create(
            producer=self.producer, name='Plain Veg',
            description='d', category='vegetables', price=2,
            stock_quantity=5, is_available=True, allergen_info='',
        )
        self.client.login(username='alcust', password='testpass123')
        response = self.client.get(reverse('products:detail', args=[product.id]))
        self.assertContains(response, 'No allergens declared')


# ======================================================================
# TC-016 — SeasonalAvailabilityTest
# ======================================================================
class SeasonalAvailabilityTest(TestCase):
    """TC-016 — seasonal date filtering on marketplace."""

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.producer = User.objects.create_user(
            username='sprod', email='s@test.local',
            password='testpass123', role='producer',
        )
        cls.customer = User.objects.create_user(
            username='scust', email='sc@test.local',
            password='testpass123', role='customer',
        )

    def test_out_of_season_product_hidden(self):
        """Product with available_until in the past not in marketplace queryset."""
        past = timezone.now().date() - timedelta(days=10)
        Product.objects.create(
            producer=self.producer, name='Out Of Season',
            description='d', category='fruit', price=3,
            stock_quantity=5, is_available=True,
            available_until=past,
        )
        self.client.login(username='scust', password='testpass123')
        response = self.client.get(reverse('marketplace'))
        names = [p.name for p in response.context['products']]
        self.assertNotIn('Out Of Season', names)

    def test_in_season_product_visible(self):
        """Product with available_from past + available_until future appears in marketplace."""
        past = timezone.now().date() - timedelta(days=5)
        future = timezone.now().date() + timedelta(days=30)
        Product.objects.create(
            producer=self.producer, name='In Season Berries',
            description='d', category='fruit', price=4,
            stock_quantity=5, is_available=True,
            available_from=past, available_until=future,
        )
        self.client.login(username='scust', password='testpass123')
        response = self.client.get(reverse('marketplace'))
        names = [p.name for p in response.context['products']]
        self.assertIn('In Season Berries', names)

    def test_no_dates_product_always_visible(self):
        """Product with no available_from/until always appears."""
        Product.objects.create(
            producer=self.producer, name='Year Round Veg',
            description='d', category='vegetables', price=2,
            stock_quantity=5, is_available=True,
        )
        self.client.login(username='scust', password='testpass123')
        response = self.client.get(reverse('marketplace'))
        names = [p.name for p in response.context['products']]
        self.assertIn('Year Round Veg', names)


# ======================================================================
# TC-019 — SurplusTest
# ======================================================================
class SurplusTest(TestCase):
    """TC-019 — surplus produce discount system."""

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.producer = User.objects.create_user(
            username='sufprod', email='suf@test.local',
            password='testpass123', role='producer',
        )
        cls.customer = User.objects.create_user(
            username='sufcust', email='sufc@test.local',
            password='testpass123', role='customer',
        )

    def test_surplus_product_shows_badge(self):
        """Product with is_surplus=True shows surplus % badge in marketplace template."""
        Product.objects.create(
            producer=self.producer, name='Surplus Tomatoes',
            description='d', category='vegetables', price=10,
            stock_quantity=5, is_available=True,
            is_surplus=True, surplus_discount_pct=25,
            surplus_expires_at=timezone.now() + timedelta(days=2),
        )
        self.client.login(username='sufcust', password='testpass123')
        response = self.client.get(reverse('marketplace'))
        # Marketplace template renders "{N}% off" for surplus products
        self.assertContains(response, '25% off')
        self.assertContains(response, 'Surplus Tomatoes')

    def test_surplus_price_applied_at_checkout(self):
        """Cart uses current_price (discounted) not full price for surplus product."""
        product = Product.objects.create(
            producer=self.producer, name='Surplus Apples',
            description='d', category='fruit', price=10,
            stock_quantity=5, is_available=True,
            is_surplus=True, surplus_discount_pct=20,
            surplus_expires_at=timezone.now() + timedelta(days=2),
        )
        self.assertEqual(product.current_price, 8)  # 10 * 0.8
        self.client.login(username='sufcust', password='testpass123')
        self.client.post(reverse('add_to_cart', args=[product.id]), data={'quantity': 2})
        response = self.client.get(reverse('view_cart'))
        # Cart total reflects discount: 2 × 8 = 16, not 2 × 10 = 20
        self.assertEqual(response.context['total'], 16)

    def test_non_surplus_product_no_badge(self):
        """Product with is_surplus=False has no surplus badge in marketplace."""
        Product.objects.create(
            producer=self.producer, name='Plain Onions',
            description='d', category='vegetables', price=5,
            stock_quantity=5, is_available=True, is_surplus=False,
        )
        self.client.login(username='sufcust', password='testpass123')
        response = self.client.get(reverse('marketplace'))
        # Find the row containing "Plain Onions" and ensure no "% off" appears with it
        # Simpler: assert there's no surplus discount badge text at all when no surplus product exists
        self.assertNotContains(response, '% off')
class MarketplaceSearchTestCase(TestCase):
    """
    Test suite for TC-005: marketplace search.
    Search matches against product name, description, and producer name.
    Case-insensitive, partial matches accepted, empty results handled.
    """

    @classmethod
    def setUpTestData(cls):
        cls.producer = User.objects.create_user(
            username='searchproducer', password='testpass123',
            email='sp@test.local', role='producer',
        )
        cls.customer = User.objects.create_user(
            username='searchcustomer', password='testpass123',
            email='sc@test.local', role='customer',
        )
        # Create a small but distinguishable product set
        cls.tomatoes = Product.objects.create(
            name='Organic Tomatoes',
            description='Fresh local tomatoes from our greenhouse',
            category='vegetables',
            price=Decimal('4.50'), stock_quantity=20,
            producer=cls.producer, is_available=True,
            is_organic=True,
        )
        cls.bread = Product.objects.create(
            name='Sourdough Bread',
            description='Hand-crafted using organic flour',
            category='bakery',
            price=Decimal('3.50'), stock_quantity=10,
            producer=cls.producer, is_available=True,
            is_organic=False,
        )
        cls.cheese = Product.objects.create(
            name='Cheddar',
            description='Aged cheese, two years old',
            category='dairy',
            price=Decimal('8.00'), stock_quantity=5,
            producer=cls.producer, is_available=True,
            is_organic=False,
        )

    def setUp(self):
        self.client.login(username='searchcustomer', password='testpass123')

    def test_search_by_product_name(self):
        """Searching for product name returns matching products"""
        response = self.client.get(reverse('marketplace'), {'q': 'tomatoes'})
        self.assertContains(response, 'Organic Tomatoes')
        self.assertNotContains(response, 'Sourdough Bread')
        self.assertNotContains(response, 'Cheddar')

    def test_search_by_description(self):
        """Searching for a word in description returns matching products"""
        response = self.client.get(reverse('marketplace'), {'q': 'greenhouse'})
        self.assertContains(response, 'Organic Tomatoes')
        self.assertNotContains(response, 'Sourdough Bread')

    def test_search_is_case_insensitive(self):
        """Search should match regardless of case"""
        response = self.client.get(reverse('marketplace'), {'q': 'TOMATOES'})
        self.assertContains(response, 'Organic Tomatoes')

        response = self.client.get(reverse('marketplace'), {'q': 'tomatoes'})
        self.assertContains(response, 'Organic Tomatoes')

        response = self.client.get(reverse('marketplace'), {'q': 'Tomatoes'})
        self.assertContains(response, 'Organic Tomatoes')

    def test_search_partial_match(self):
        """Partial keywords should match (icontains behaviour)"""
        response = self.client.get(reverse('marketplace'), {'q': 'sour'})
        self.assertContains(response, 'Sourdough Bread')

    def test_search_returns_no_results_for_unknown_term(self):
        """Search for non-existent term returns empty product list"""
        response = self.client.get(reverse('marketplace'), {'q': 'asparagus'})
        self.assertNotContains(response, 'Organic Tomatoes')
        self.assertNotContains(response, 'Sourdough Bread')
        self.assertNotContains(response, 'Cheddar')

    def test_search_across_name_and_description(self):
        """Term appearing in description (not name) should still match"""
        # 'organic' appears in tomatoes (name+description) AND bread (description only)
        response = self.client.get(reverse('marketplace'), {'q': 'organic'})
        self.assertContains(response, 'Organic Tomatoes')
        self.assertContains(response, 'Sourdough Bread')

    def test_empty_query_returns_all_products(self):
        """No search query returns the full product list"""
        response = self.client.get(reverse('marketplace'))
        self.assertContains(response, 'Organic Tomatoes')
        self.assertContains(response, 'Sourdough Bread')
        self.assertContains(response, 'Cheddar')

    def test_search_unavailable_products_excluded(self):
        """is_available=False products should never appear, even on matching search"""
        Product.objects.create(
            name='Hidden Item',
            description='unavailable',
            category='vegetables',
            price=Decimal('1.00'), stock_quantity=10,
            producer=self.producer, is_available=False,
        )
        response = self.client.get(reverse('marketplace'), {'q': 'hidden'})
        self.assertNotContains(response, 'Hidden Item')


class ProductListingTestCase(TestCase):
    # TC-003: Producer can create a product listing
    # Checks that products are correctly linked to producers
    # and that availability is respected in the marketplace

    @classmethod
    def setUpTestData(cls):
        cls.producer = User.objects.create_user(
            username='listingproducer', password='testpass123',
            email='lp@test.local', role='producer',
        )
        cls.customer = User.objects.create_user(
            username='listingcustomer', password='testpass123',
            email='lc@test.local', role='customer',
        )

    def test_producer_can_access_add_product_page(self):
        # The add product page should be accessible to producers
        self.client.login(username='listingproducer', password='testpass123')
        response = self.client.get(reverse('products:add'))
        self.assertEqual(response.status_code, 200)

    def test_customer_cannot_access_add_product_page(self):
        # Customers should not be able to get to the product creation form
        self.client.login(username='listingcustomer', password='testpass123')
        response = self.client.get(reverse('products:add'))
        self.assertEqual(response.status_code, 302)

    def test_product_is_linked_to_the_producer_who_created_it(self):
        # When a product is created it should belong to the correct producer
        product = Product.objects.create(
            producer=self.producer,
            name='Organic Free Range Eggs',
            description='Fresh organic eggs from free-range hens collected daily',
            category='dairy',
            price=Decimal('3.50'),
            stock_quantity=50,
            allergen_info='eggs',
            is_available=True,
            is_organic=True,
        )
        self.assertEqual(product.producer, self.producer)

    def test_product_is_visible_to_customers_after_creation(self):
        # Once created and marked available the product should show in the marketplace
        Product.objects.create(
            producer=self.producer,
            name='Fresh Honey',
            description='Local wildflower honey',
            category='preserves',
            price=Decimal('6.00'),
            stock_quantity=20,
            is_available=True,
        )
        self.client.login(username='listingcustomer', password='testpass123')
        response = self.client.get(reverse('marketplace'), {'q': 'Fresh Honey'})
        self.assertContains(response, 'Fresh Honey')

    def test_unavailable_product_is_not_visible_to_customers(self):
        # Products marked as unavailable should show 0 results in the marketplace
        Product.objects.create(
            producer=self.producer,
            name='Out Of Season Strawberries',
            description='Strawberries',
            category='fruit',
            price=Decimal('4.00'),
            stock_quantity=0,
            is_available=False,
        )
        self.client.login(username='listingcustomer', password='testpass123')
        response = self.client.get(reverse('marketplace'), {'q': 'Out Of Season Strawberries'})
        # The search term appears in the search box but 0 products should be returned
        self.assertContains(response, '0 results found')


class CategoryBrowsingTestCase(TestCase):
    # TC-004: Category browsing in the marketplace
    # Customers should be able to filter by category and only see
    # products from that specific category

    @classmethod
    def setUpTestData(cls):
        cls.producer = User.objects.create_user(
            username='categoryproducer', password='testpass123',
            email='cp@test.local', role='producer',
        )
        cls.customer = User.objects.create_user(
            username='categorycustomer', password='testpass123',
            email='cc@test.local', role='customer',
        )
        # Create one product in each category so we can test filtering
        cls.veggie = Product.objects.create(
            producer=cls.producer, name='Category Carrots',
            description='Fresh carrots', category='vegetables',
            price=Decimal('2.00'), stock_quantity=30, is_available=True,
        )
        cls.dairy = Product.objects.create(
            producer=cls.producer, name='Category Cheese',
            description='Aged cheddar', category='dairy',
            price=Decimal('7.00'), stock_quantity=15, is_available=True,
        )
        cls.bakery = Product.objects.create(
            producer=cls.producer, name='Category Bread',
            description='Sourdough loaf', category='bakery',
            price=Decimal('3.50'), stock_quantity=10, is_available=True,
        )

    def setUp(self):
        self.client.login(username='categorycustomer', password='testpass123')

    def test_filtering_by_vegetables_only_shows_vegetables(self):
        # Applying the vegetables filter should hide dairy and bakery products
        response = self.client.get(reverse('marketplace'), {'category': 'vegetables'})
        self.assertContains(response, 'Category Carrots')
        self.assertNotContains(response, 'Category Cheese')
        self.assertNotContains(response, 'Category Bread')

    def test_filtering_by_dairy_only_shows_dairy(self):
        # Applying the dairy filter should hide everything that isnt dairy
        response = self.client.get(reverse('marketplace'), {'category': 'dairy'})
        self.assertContains(response, 'Category Cheese')
        self.assertNotContains(response, 'Category Carrots')
        self.assertNotContains(response, 'Category Bread')

    def test_no_category_filter_shows_all_products(self):
        # Without a category filter all available products should be shown
        response = self.client.get(reverse('marketplace'))
        self.assertContains(response, 'Category Carrots')
        self.assertContains(response, 'Category Cheese')
        self.assertContains(response, 'Category Bread')


class InventoryManagementTestCase(TestCase):
    # TC-011: Producer can update product stock and availability
    # Tests that stock changes save correctly and the marketplace
    # reflects those changes immediately for customers

    @classmethod
    def setUpTestData(cls):
        cls.producer = User.objects.create_user(
            username='inventoryproducer', password='testpass123',
            email='ip@test.local', role='producer',
        )
        cls.customer = User.objects.create_user(
            username='inventorycustomer', password='testpass123',
            email='ic@test.local', role='customer',
        )

    def _make_product(self, **overrides):
        # Helper to create a basic product with sensible defaults
        defaults = {
            'producer': self.producer,
            'name': 'Inventory Test Product',
            'description': 'x',
            'category': 'vegetables',
            'price': Decimal('3.00'),
            'stock_quantity': 20,
            'is_available': True,
        }
        defaults.update(overrides)
        return Product.objects.create(**defaults)

    def test_producer_can_update_stock_quantity(self):
        # Updating stock quantity directly on the model should persist correctly
        product = self._make_product(stock_quantity=20)
        product.stock_quantity = 35
        product.save()
        product.refresh_from_db()
        self.assertEqual(product.stock_quantity, 35)

    def test_producer_can_mark_product_as_unavailable(self):
        # Setting is_available to False should persist and hide from customers
        product = self._make_product(is_available=True)
        product.is_available = False
        product.save()
        product.refresh_from_db()
        self.assertFalse(product.is_available)

    def test_unavailable_product_hidden_from_marketplace(self):
        # Once marked unavailable the marketplace should return 0 results
        self._make_product(name='Hidden Tomatoes', is_available=False)
        self.client.login(username='inventorycustomer', password='testpass123')
        response = self.client.get(reverse('marketplace'), {'q': 'Hidden Tomatoes'})
        # Search term appears in the search box but no product cards should be shown
        self.assertContains(response, '0 results found')

    def test_producer_can_only_edit_their_own_products(self):
        # A producer trying to edit another producers product should get a 404
        other_producer = User.objects.create_user(
            username='otherinvproducer', password='testpass123',
            email='other@test.local', role='producer',
        )
        other_product = Product.objects.create(
            producer=other_producer, name='Not Mine',
            description='x', category='vegetables',
            price=Decimal('1.00'), stock_quantity=5, is_available=True,
        )
        self.client.login(username='inventoryproducer', password='testpass123')
        response = self.client.get(reverse('products:edit', args=[other_product.pk]))
        self.assertEqual(response.status_code, 404)

class OrganicFilterTestCase(TestCase):
    # TC-014: Organic certification filter in the marketplace
    # Customers should be able to filter to only see organic products
    # and non-certified items should be excluded from those results

    @classmethod
    def setUpTestData(cls):
        cls.producer = User.objects.create_user(
            username='organicproducer', password='testpass123',
            email='op@test.local', role='producer',
        )
        cls.customer = User.objects.create_user(
            username='organiccustomer', password='testpass123',
            email='oc@test.local', role='customer',
        )
        # One organic and one non-organic so we can test the filter works both ways
        cls.organic_product = Product.objects.create(
            producer=cls.producer, name='Certified Organic Spinach',
            description='Certified organic', category='vegetables',
            price=Decimal('3.00'), stock_quantity=20,
            is_available=True, is_organic=True,
        )
        cls.non_organic_product = Product.objects.create(
            producer=cls.producer, name='Regular Spinach',
            description='Conventional', category='vegetables',
            price=Decimal('2.00'), stock_quantity=20,
            is_available=True, is_organic=False,
        )

    def setUp(self):
        self.client.login(username='organiccustomer', password='testpass123')

    def test_organic_filter_only_shows_organic_products(self):
        # When organic filter is on only certified products should appear
        response = self.client.get(reverse('marketplace'), {'organic': 'on'})
        self.assertContains(response, 'Certified Organic Spinach')
        self.assertNotContains(response, 'Regular Spinach')

    def test_no_organic_filter_shows_all_products(self):
        # Without the filter both organic and non-organic should be visible
        response = self.client.get(reverse('marketplace'))
        self.assertContains(response, 'Certified Organic Spinach')
        self.assertContains(response, 'Regular Spinach')

    def test_organic_flag_is_correctly_stored_on_product(self):
        # The is_organic field should be saved properly when set on a product
        self.assertTrue(self.organic_product.is_organic)
        self.assertFalse(self.non_organic_product.is_organic)


class AllergenDisplayTestCase(TestCase):
    # TC-015: Allergen information is displayed on product detail pages
    # This is a critical food safety requirement - customers need to see
    # allergens clearly before they buy anything

    @classmethod
    def setUpTestData(cls):
        cls.producer = User.objects.create_user(
            username='allergenproducer', password='testpass123',
            email='ap@test.local', role='producer',
        )
        cls.customer = User.objects.create_user(
            username='allergencustomer', password='testpass123',
            email='ac@test.local', role='customer',
        )
        # Product with a single dairy allergen
        cls.cheese = Product.objects.create(
            producer=cls.producer, name='Cheddar Cheese',
            description='Aged cheddar', category='dairy',
            price=Decimal('8.00'), stock_quantity=10,
            is_available=True, allergen_info='milk',
        )
        # Product with multiple allergens to test comma separated parsing
        cls.walnut_bread = Product.objects.create(
            producer=cls.producer, name='Walnut Bread',
            description='Handmade bread with walnuts', category='bakery',
            price=Decimal('3.50'), stock_quantity=8,
            is_available=True, allergen_info='gluten,nuts',
        )
        # Product with no allergens at all
        cls.apples = Product.objects.create(
            producer=cls.producer, name='Fresh Apples',
            description='Cox apples from the orchard', category='fruit',
            price=Decimal('2.50'), stock_quantity=30,
            is_available=True, allergen_info='',
        )

    def setUp(self):
        self.client.login(username='allergencustomer', password='testpass123')

    def test_allergen_info_is_stored_correctly_on_product(self):
        # Allergen data should be saved to the product correctly
        self.assertEqual(self.cheese.allergen_info, 'milk')
        self.assertEqual(self.walnut_bread.allergen_info, 'gluten,nuts')

    def test_allergen_list_property_parses_correctly(self):
        # The allergen_list property should split the comma separated string into a list
        self.assertIn('milk', self.cheese.allergen_list)
        self.assertIn('gluten', self.walnut_bread.allergen_list)
        self.assertIn('nuts', self.walnut_bread.allergen_list)

    def test_product_with_no_allergens_has_empty_allergen_list(self):
        # A product with no allergens should return an empty list not crash
        self.assertEqual(self.apples.allergen_list, [])

    def test_product_detail_page_loads_for_product_with_allergens(self):
        # The product detail page should load without errors for allergen products
        response = self.client.get(reverse('products:detail', args=[self.cheese.pk]))
        self.assertEqual(response.status_code, 200)

    def test_hide_allergens_filter_removes_matching_products(self):
        # If a customer has set milk as an allergen to avoid then cheese should
        # not appear when the hide allergens filter is active
        self.customer.avoided_allergens = 'milk'
        self.customer.save()
        response = self.client.get(reverse('marketplace'), {'hide_allergens': 'on'})
        self.assertNotContains(response, 'Cheddar Cheese')
        # Apples have no allergens so should still be visible
        self.assertContains(response, 'Fresh Apples')


class SurplusDealsTestCase(TestCase):
    # TC-019: Producer marks products as surplus with a discount
    # Surplus products should appear in the marketplace with correct discounted
    # pricing and expire automatically after the set time

    @classmethod
    def setUpTestData(cls):
        cls.producer = User.objects.create_user(
            username='surplusproducer', password='testpass123',
            email='sp@test.local', role='producer',
        )
        cls.customer = User.objects.create_user(
            username='surpluscustomer', password='testpass123',
            email='sc@test.local', role='customer',
        )

    def _make_surplus_product(self, **overrides):
        # Helper to create a surplus product with a 48 hour expiry by default
        from django.utils import timezone
        defaults = {
            'producer': self.producer,
            'name': 'Surplus Lettuce',
            'description': 'Perfect condition must sell quickly',
            'category': 'vegetables',
            'price': Decimal('2.00'),
            'stock_quantity': 50,
            'is_available': True,
            'is_surplus': True,
            'surplus_discount_pct': 30,
            'surplus_expires_at': timezone.now() + timezone.timedelta(hours=48),
        }
        defaults.update(overrides)
        return Product.objects.create(**defaults)

    def test_surplus_product_shows_in_surplus_filter(self):
        # When filtering for surplus deals the surplus product should appear
        self._make_surplus_product()
        self.client.login(username='surpluscustomer', password='testpass123')
        response = self.client.get(reverse('marketplace'), {'surplus': 'on'})
        self.assertContains(response, 'Surplus Lettuce')

    def test_non_surplus_product_does_not_show_in_surplus_filter(self):
        # Regular products should not show up when the surplus filter is active
        Product.objects.create(
            producer=self.producer, name='Normal Carrots',
            description='Just regular carrots', category='vegetables',
            price=Decimal('2.00'), stock_quantity=20,
            is_available=True, is_surplus=False,
        )
        self.client.login(username='surpluscustomer', password='testpass123')
        response = self.client.get(reverse('marketplace'), {'surplus': 'on'})
        self.assertNotContains(response, 'Normal Carrots')

    def test_discounted_price_is_calculated_correctly(self):
        # 30% off 2.00 should give 1.40 - checking the current_price property works
        product = self._make_surplus_product(price=Decimal('2.00'), surplus_discount_pct=30)
        expected_price = Decimal('2.00') * Decimal('0.70')
        self.assertEqual(product.current_price, expected_price)

    def test_expired_surplus_deal_is_not_active(self):
        # A surplus deal past its expiry time should not be flagged as active
        from django.utils import timezone
        product = self._make_surplus_product(
            surplus_expires_at=timezone.now() - timezone.timedelta(hours=1)
        )
        self.assertFalse(product.is_active_surplus)

    def test_active_surplus_deal_is_recognised(self):
        # A surplus deal with a future expiry should be flagged as active
        product = self._make_surplus_product()
        self.assertTrue(product.is_active_surplus)

    def test_product_without_surplus_flag_is_not_active_surplus(self):
        # A regular product should never be treated as a surplus deal
        product = Product.objects.create(
            producer=self.producer, name='Regular Potato',
            description='x', category='vegetables',
            price=Decimal('1.50'), stock_quantity=20,
            is_available=True, is_surplus=False,
        )
        self.assertFalse(product.is_active_surplus)
