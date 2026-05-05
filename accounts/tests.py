from django.test import TestCase

# Create your tests here.
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import CustomUser
from producers.models import ProducerProfile
from products.models import Product

User = get_user_model()


class ProducerRegistrationTest(TestCase):
    """
    Test suite for TC-001: Producer registration.
    Producer can register, log in, and is assigned the producer role.
    """

    def test_producer_registers_with_valid_data(self):
        """POST to register creates a producer user and redirects"""
        response = self.client.post(reverse('accounts:register'), data={
            'username': 'testproducer',
            'email': 'test@producer.local',
            'role': 'producer',
            'password1': 'SecureP@ss123!',
            'password2': 'SecureP@ss123!',
        })
        self.assertEqual(response.status_code, 302)
        user = User.objects.filter(username='testproducer').first()
        self.assertIsNotNone(user)
        self.assertEqual(user.role, 'producer')

    def test_producer_can_login_after_registration(self):
        """Producer should be able to authenticate with their registered credentials"""
        self.client.post(reverse('accounts:register'), data={
            'username': 'loginproducer',
            'email': 'login@producer.local',
            'role': 'producer',
            'password1': 'SecureP@ss123!',
            'password2': 'SecureP@ss123!',
        })
        # New client to clear the auto-login that happens on register
        from django.test import Client
        client = Client()
        logged_in = client.login(username='loginproducer', password='SecureP@ss123!')
        self.assertTrue(logged_in)

    def test_duplicate_username_rejected(self):
        """Second registration with same username fails, user not duplicated"""
        self.client.post(reverse('accounts:register'), data={
            'username': 'dupeuser',
            'email': 'first@test.local',
            'role': 'producer',
            'password1': 'SecureP@ss123!',
            'password2': 'SecureP@ss123!',
        })
        response = self.client.post(reverse('accounts:register'), data={
            'username': 'dupeuser',
            'email': 'second@test.local',
            'role': 'producer',
            'password1': 'AnotherP@ss456!',
            'password2': 'AnotherP@ss456!',
        })
        # Form re-renders with errors (200) instead of redirecting
        self.assertEqual(response.status_code, 200)
        self.assertEqual(User.objects.filter(username='dupeuser').count(), 1)

    def test_password_mismatch_rejected(self):
        """Password and confirmation must match"""
        response = self.client.post(reverse('accounts:register'), data={
            'username': 'mismatchuser',
            'email': 'm@test.local',
            'role': 'producer',
            'password1': 'SecureP@ss123!',
            'password2': 'DifferentP@ss!',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username='mismatchuser').exists())

    def test_producer_profile_auto_created(self):
        """ProducerProfile should auto-create when producer registers"""
        self.client.post(reverse('accounts:register'), data={
            'username': 'profileproducer',
            'email': 'pp@test.local',
            'role': 'producer',
            'password1': 'SecureP@ss123!',
            'password2': 'SecureP@ss123!',
        })
        user = User.objects.get(username='profileproducer')
        self.assertTrue(ProducerProfile.objects.filter(user=user).exists())


class CustomerRegistrationTest(TestCase):
    """
    Test suite for TC-002: Customer registration.
    Customer can register and authenticate with their credentials.
    Note: postcode and delivery address are added later via the profile page,
    not at registration.
    """

    def test_customer_registers_with_valid_data(self):
        """POST to register creates a customer user and redirects"""
        response = self.client.post(reverse('accounts:register'), data={
            'username': 'testcustomer',
            'email': 'test@customer.local',
            'role': 'customer',
            'password1': 'SecureP@ss123!',
            'password2': 'SecureP@ss123!',
        })
        self.assertEqual(response.status_code, 302)
        user = User.objects.filter(username='testcustomer').first()
        self.assertIsNotNone(user)
        self.assertEqual(user.role, 'customer')

    def test_customer_can_login_after_registration(self):
        """Customer should authenticate with their registered credentials"""
        self.client.post(reverse('accounts:register'), data={
            'username': 'logincustomer',
            'email': 'login@customer.local',
            'role': 'customer',
            'password1': 'SecureP@ss123!',
            'password2': 'SecureP@ss123!',
        })
        from django.test import Client
        client = Client()
        logged_in = client.login(username='logincustomer', password='SecureP@ss123!')
        self.assertTrue(logged_in)

    def test_wrong_password_login_fails(self):
        """Wrong password should fail authentication"""
        self.client.post(reverse('accounts:register'), data={
            'username': 'wrongpwcustomer',
            'email': 'wp@customer.local',
            'role': 'customer',
            'password1': 'SecureP@ss123!',
            'password2': 'SecureP@ss123!',
        })
        from django.test import Client
        client = Client()
        logged_in = client.login(username='wrongpwcustomer', password='WrongPassword!')
        self.assertFalse(logged_in)

    def test_customer_postcode_saved_via_profile(self):
        """Customer can save their postcode via the profile page after registration"""
        # Register
        self.client.post(reverse('accounts:register'), data={
            'username': 'pccustomer',
            'email': 'pc@customer.local',
            'role': 'customer',
            'password1': 'SecureP@ss123!',
            'password2': 'SecureP@ss123!',
        })
        # Now log in and update profile (auto-login should be active from register, but explicit here)
        self.client.login(username='pccustomer', password='SecureP@ss123!')
        
        # POST to profile with postcode — needs PostcodesService mocked since it's external
        from unittest.mock import patch
        with patch('accounts.views.PostcodesService') as mock_service_class:
            mock_service = mock_service_class.return_value
            mock_service.lookup_postcode.return_value = {
                'postcode': 'BS1 5JG',
                'latitude': 51.45,
                'longitude': -2.59,
                'town': 'Bristol',
            }
            self.client.post(reverse('accounts:profile'), data={
                'email': 'pc@customer.local',
                'postcode': 'BS1 5JG',
            })
        
        user = User.objects.get(username='pccustomer')
        self.assertEqual(user.postcode, 'BS1 5JG')


class AuthorisationTest(TestCase):
    """
    Test suite for TC-022 (MANDATORY): Authentication and authorisation.
    Covers password security (hashing, complexity), role-based access control,
    and session management.
    """

    @classmethod
    def setUpTestData(cls):
        cls.customer = User.objects.create_user(
            username='authcustomer',
            password='SecureP@ss123!',
            email='c@test.local',
            role='customer',
        )
        cls.producer = User.objects.create_user(
            username='authproducer',
            password='SecureP@ss123!',
            email='p@test.local',
            role='producer',
        )
        cls.other_producer = User.objects.create_user(
            username='authproducer2',
            password='SecureP@ss123!',
            email='p2@test.local',
            role='producer',
        )

    # -- Password Security --

    def test_password_stored_hashed(self):
        """Stored password should not equal the raw password"""
        user = User.objects.get(username='authcustomer')
        self.assertNotEqual(user.password, 'SecureP@ss123!')
        # Should look like a Django hash (algorithm$salt$hash)
        self.assertIn('$', user.password)

    def test_weak_password_rejected_at_registration(self):
        """Django's password validators should reject weak passwords"""
        response = self.client.post(reverse('accounts:register'), data={
            'username': 'weakpwuser',
            'email': 'w@test.local',
            'role': 'customer',
            'password1': '123',
            'password2': '123',
        })
        # Form re-renders with errors instead of redirecting
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username='weakpwuser').exists())

    # -- Authorisation: Role-Based Access --

    def test_customer_blocked_from_producer_dashboard(self):
        """Customer hitting producer dashboard should be redirected to marketplace"""
        self.client.login(username='authcustomer', password='SecureP@ss123!')
        response = self.client.get(reverse('producer_dashboard'))
        self.assertEqual(response.status_code, 302)
        # Should redirect to marketplace, not produce a 200
        self.assertIn(response.url, ['/', reverse('marketplace')])

    def test_producer_can_access_own_dashboard(self):
        """Producer should reach the dashboard with a 200"""
        self.client.login(username='authproducer', password='SecureP@ss123!')
        response = self.client.get(reverse('producer_dashboard'))
        self.assertEqual(response.status_code, 200)

    def test_unauthenticated_redirected_from_dashboard(self):
        """No session = redirect to login"""
        response = self.client.get(reverse('producer_dashboard'))
        self.assertEqual(response.status_code, 302)
        # Django's @login_required redirects to LOGIN_URL
        self.assertIn('login', response.url.lower())

    def test_producer_cannot_access_other_producers_orders(self):
        """Producer trying to act on another producer's order should be blocked"""
        # Create an order for other_producer's product, then have authproducer try to ship it
        from orders.models import Order, OrderItem
        from datetime import timedelta
        from django.utils import timezone
        from decimal import Decimal

        product = Product.objects.create(
            name='Other Producer Product',
            description='x', category='vegetables',
            price=Decimal('5.00'), stock_quantity=10,
            producer=self.other_producer, is_available=True,
        )
        order = Order.objects.create(
            customer=self.customer,
            total=Decimal('5.00'),
            status='confirmed',
            delivery_date=timezone.now().date() + timedelta(days=3),
            delivery_address='Bristol',
        )
        OrderItem.objects.create(
            order=order, product=product,
            quantity=1, price=product.price,
        )

        # Log in as authproducer (not the one who owns the product)
        self.client.login(username='authproducer', password='SecureP@ss123!')
        response = self.client.post(reverse('ship_order', args=[order.id]))
        # Should be redirected/blocked (302), not allowed to act on the order
        self.assertEqual(response.status_code, 302)
        # Order shouldn't be in 'dispatched' state — wrong producer can't ship
        order.refresh_from_db()
        self.assertNotEqual(order.status, 'dispatched')

    # -- Session Management --

    def test_logout_terminates_session(self):
        """After logout, protected pages require login again"""
        self.client.login(username='authproducer', password='SecureP@ss123!')
        # Verify logged in
        response = self.client.get(reverse('producer_dashboard'))
        self.assertEqual(response.status_code, 200)
        # Log out
        self.client.get(reverse('accounts:logout'))
        # Now protected page redirects to login
        response = self.client.get(reverse('producer_dashboard'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('login', response.url.lower())

    def test_failed_login_does_not_create_session(self):
        """Wrong password keeps user unauthenticated"""
        self.client.post(reverse('accounts:login'), data={
            'username': 'authcustomer',
            'password': 'WrongPassword!',
        })
        # Should still be redirected from protected pages
        response = self.client.get(reverse('producer_dashboard'))
        self.assertEqual(response.status_code, 302)

    def test_customer_blocked_from_add_product(self):
        """Customer hitting product add URL should be blocked"""
        self.client.login(username='authcustomer', password='SecureP@ss123!')
        response = self.client.get(reverse('products:add'))
        self.assertEqual(response.status_code, 302)