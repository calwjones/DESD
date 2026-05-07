from datetime import date, timedelta
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from orders.models import Order, OrderItem, Payment, PaymentSplit, Settlement
from products.models import Product
from producers.models import Recipe, FarmStory, ProducerProfile
from decimal import Decimal


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




class RecipeAndFarmStoryTestCase(TestCase):
    # TC-020: Producer can create recipes and farm stories
    # Tests that producers can add content linked to their products
    # and that it appears correctly on their public profile page

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.producer = User.objects.create_user(
            username='contentproducer', password='testpass123',
            email='cp@test.local', role='producer',
        )
        cls.customer = User.objects.create_user(
            username='contentcustomer', password='testpass123',
            email='cc@test.local', role='customer',
        )
        # Producer needs a profile or the public profile page will 404
        # Using get_or_create because the signal may have already created one on user save
        cls.profile, _ = ProducerProfile.objects.get_or_create(
            user=cls.producer,
            defaults={'business_name': 'Content Farm'},
        )
        cls.product = Product.objects.create(
            producer=cls.producer,
            name='Roasting Carrots',
            description='Great for roasting',
            category='vegetables',
            price=Decimal('2.00'),
            stock_quantity=20,
            is_available=True,
        )

    def test_producer_can_create_a_recipe(self):
        # Submitting the recipe form should save the recipe to the database
        self.client.login(username='contentproducer', password='testpass123')
        self.client.post(reverse('producers:recipe_add'), {
            'title': 'Roasted Root Vegetable Medley',
            'description': 'A warming autumn dish',
            'ingredients': 'Carrots parsnips olive oil rosemary',
            'method': 'Chop toss in oil roast at 200c for 40 mins',
            'seasonal_tag': 'autumn',
            'product': self.product.pk,
        })
        self.assertTrue(Recipe.objects.filter(title='Roasted Root Vegetable Medley').exists())

    def test_recipe_is_linked_to_the_correct_producer(self):
        # Recipes should be owned by the producer who created them
        self.client.login(username='contentproducer', password='testpass123')
        self.client.post(reverse('producers:recipe_add'), {
            'title': 'Carrot Soup',
            'description': 'Simple carrot soup',
            'ingredients': 'Carrots onion stock',
            'method': 'Chop and simmer for 30 minutes',
            'seasonal_tag': 'year_round',
        })
        recipe = Recipe.objects.get(title='Carrot Soup')
        self.assertEqual(recipe.producer, self.producer)

    def test_recipe_can_be_linked_to_a_product(self):
        # A recipe can reference a specific product in the producers range
        recipe = Recipe.objects.create(
            producer=self.producer,
            title='Carrot Cake',
            description='Classic carrot cake',
            ingredients='Carrots flour eggs sugar',
            method='Mix and bake at 180c',
            product=self.product,
            seasonal_tag='year_round',
        )
        self.assertEqual(recipe.product, self.product)

    def test_customer_cannot_access_recipe_add_page(self):
        # Only producers should be able to add recipes not customers
        self.client.login(username='contentcustomer', password='testpass123')
        response = self.client.get(reverse('producers:recipe_add'))
        self.assertEqual(response.status_code, 302)

    def test_producer_can_create_a_farm_story(self):
        # Submitting the story form should save the farm story to the database
        self.client.login(username='contentproducer', password='testpass123')
        self.client.post(reverse('producers:story_add'), {
            'title': 'Harvest Season Update',
            'body': 'This has been an incredible harvest season for us at Content Farm',
        })
        self.assertTrue(FarmStory.objects.filter(title='Harvest Season Update').exists())

    def test_farm_story_is_linked_to_the_correct_producer(self):
        # Farm stories should belong to the producer who wrote them
        self.client.login(username='contentproducer', password='testpass123')
        self.client.post(reverse('producers:story_add'), {
            'title': 'A Day With Our Bees',
            'body': 'We spent the morning checking on our beehives',
        })
        story = FarmStory.objects.get(title='A Day With Our Bees')
        self.assertEqual(story.producer, self.producer)

    def test_recipes_appear_on_producer_public_profile(self):
        # Customers should be able to see a producers recipes on their profile page
        Recipe.objects.create(
            producer=self.producer,
            title='Visible Recipe',
            description='Should appear on profile',
            ingredients='Carrots',
            method='Cook them',
            seasonal_tag='year_round',
        )
        self.client.login(username='contentcustomer', password='testpass123')
        response = self.client.get(
            reverse('producers:producer_public_profile', args=[self.producer.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Visible Recipe')

    def test_farm_stories_appear_on_producer_public_profile(self):
        # Farm stories should also be visible on the producers public profile page
        FarmStory.objects.create(
            producer=self.producer,
            title='Visible Farm Story',
            body='A story about our farm',
        )
        self.client.login(username='contentcustomer', password='testpass123')
        response = self.client.get(
            reverse('producers:producer_public_profile', args=[self.producer.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Visible Farm Story')