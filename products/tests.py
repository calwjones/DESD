from datetime import timedelta
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from products.models import Product

User = get_user_model()




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