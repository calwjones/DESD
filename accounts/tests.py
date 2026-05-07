from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

User = get_user_model()


class ProducerRegistrationTestCase(TestCase):
    # TC-001: Producer account registration
    # Checks that a producer can sign up, gets the right role assigned,
    # and gets redirected to the producer dashboard after login

    def test_producer_can_register_with_valid_details(self):
        # Submit the registration form with a producer role
        response = self.client.post(reverse('accounts:register'), {
            'username': 'bristolvalleyfarm',
            'email': 'jane.smith@bristolvalleyfarm.com',
            'role': 'producer',
            'password1': 'SecurePass123!',
            'password2': 'SecurePass123!',
        })
        # Should redirect after successful registration, not re-render the form
        self.assertNotEqual(response.status_code, 200)
        self.assertTrue(User.objects.filter(username='bristolvalleyfarm').exists())

    def test_producer_account_gets_producer_role(self):
        # Make sure the role field is actually saved correctly
        self.client.post(reverse('accounts:register'), {
            'username': 'bristolvalleyfarm',
            'email': 'jane@farm.com',
            'role': 'producer',
            'password1': 'SecurePass123!',
            'password2': 'SecurePass123!',
        })
        user = User.objects.get(username='bristolvalleyfarm')
        self.assertEqual(user.role, 'producer')

    def test_producer_password_is_hashed_not_plaintext(self):
        # Passwords should never be stored in plain text in the database
        self.client.post(reverse('accounts:register'), {
            'username': 'bristolvalleyfarm',
            'email': 'jane@farm.com',
            'role': 'producer',
            'password1': 'SecurePass123!',
            'password2': 'SecurePass123!',
        })
        user = User.objects.get(username='bristolvalleyfarm')
        # Django hashes passwords - the stored value should never be the raw string
        self.assertNotEqual(user.password, 'SecurePass123!')
        self.assertTrue(user.has_usable_password())

    def test_producer_can_log_in_after_registration(self):
        # Register first then log out and try logging back in
        self.client.post(reverse('accounts:register'), {
            'username': 'bristolvalleyfarm',
            'email': 'jane@farm.com',
            'role': 'producer',
            'password1': 'SecurePass123!',
            'password2': 'SecurePass123!',
        })
        self.client.logout()
        response = self.client.post(reverse('accounts:login'), {
            'username': 'bristolvalleyfarm',
            'password': 'SecurePass123!',
        })
        # Successful login should redirect away from the login page
        self.assertEqual(response.status_code, 302)

    def test_registration_fails_with_mismatched_passwords(self):
        # Passwords that dont match should re-render the form with an error
        response = self.client.post(reverse('accounts:register'), {
            'username': 'bristolvalleyfarm',
            'email': 'jane@farm.com',
            'role': 'producer',
            'password1': 'SecurePass123!',
            'password2': 'DifferentPass456!',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username='bristolvalleyfarm').exists())

    def test_registration_fails_with_weak_password(self):
        # Weak passwords like 123 should be rejected by Djangos password validators
        response = self.client.post(reverse('accounts:register'), {
            'username': 'bristolvalleyfarm',
            'email': 'jane@farm.com',
            'role': 'producer',
            'password1': '123',
            'password2': '123',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username='bristolvalleyfarm').exists())


class CustomerRegistrationTestCase(TestCase):
    # TC-002: Customer account registration
    # Makes sure customers can register and end up with the correct role
    # and get redirected to the marketplace

    def test_customer_can_register_with_valid_details(self):
        response = self.client.post(reverse('accounts:register'), {
            'username': 'robertjohnson',
            'email': 'robert.johnson@email.com',
            'role': 'customer',
            'password1': 'SecurePass123!',
            'password2': 'SecurePass123!',
        })
        self.assertNotEqual(response.status_code, 200)
        self.assertTrue(User.objects.filter(username='robertjohnson').exists())

    def test_customer_account_gets_customer_role(self):
        self.client.post(reverse('accounts:register'), {
            'username': 'robertjohnson',
            'email': 'robert@email.com',
            'role': 'customer',
            'password1': 'SecurePass123!',
            'password2': 'SecurePass123!',
        })
        user = User.objects.get(username='robertjohnson')
        self.assertEqual(user.role, 'customer')

    def test_customer_redirected_to_marketplace_after_registration(self):
        # Customers should land on the marketplace not the producer dashboard
        response = self.client.post(reverse('accounts:register'), {
            'username': 'robertjohnson',
            'email': 'robert@email.com',
            'role': 'customer',
            'password1': 'SecurePass123!',
            'password2': 'SecurePass123!',
        })
        self.assertRedirects(response, reverse('marketplace'))

    def test_producer_redirected_to_dashboard_after_registration(self):
        # Producers should land on the producer dashboard not the marketplace
        response = self.client.post(reverse('accounts:register'), {
            'username': 'farmproducer',
            'email': 'farm@producer.com',
            'role': 'producer',
            'password1': 'SecurePass123!',
            'password2': 'SecurePass123!',
        })
        self.assertRedirects(response, reverse('producer_dashboard'))

    def test_duplicate_username_rejected(self):
        # Cant register two accounts with the same username
        User.objects.create_user(username='robertjohnson', password='pass', role='customer')
        response = self.client.post(reverse('accounts:register'), {
            'username': 'robertjohnson',
            'email': 'different@email.com',
            'role': 'customer',
            'password1': 'SecurePass123!',
            'password2': 'SecurePass123!',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(User.objects.filter(username='robertjohnson').count(), 1)


class AuthenticationSecurityTestCase(TestCase):
    # TC-022: Authentication and authorisation security
    # Tests login, logout, role based access control and that users
    # cannot access things they are not supposed to

    @classmethod
    def setUpTestData(cls):
        cls.customer = User.objects.create_user(
            username='testcustomer', password='SecurePass123!', role='customer'
        )
        cls.producer = User.objects.create_user(
            username='testproducer', password='SecurePass123!', role='producer'
        )

    def test_login_with_correct_credentials_succeeds(self):
        response = self.client.post(reverse('accounts:login'), {
            'username': 'testcustomer',
            'password': 'SecurePass123!',
        })
        # Successful login should redirect away from the login page
        self.assertEqual(response.status_code, 302)

    def test_login_with_wrong_password_fails(self):
        response = self.client.post(reverse('accounts:login'), {
            'username': 'testcustomer',
            'password': 'WrongPassword!',
        })
        # Should re-render the login form not redirect
        self.assertEqual(response.status_code, 200)

    def test_login_error_does_not_reveal_if_user_exists(self):
        # Error message should be generic and not confirm whether a username exists
        # as that would leak information useful for attacks
        response = self.client.post(reverse('accounts:login'), {
            'username': 'nonexistentuser',
            'password': 'anypassword',
        })
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'does not exist')

    def test_unauthenticated_user_redirected_from_marketplace(self):
        # Pages that require login should redirect anonymous users to the login page
        response = self.client.get(reverse('marketplace'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('login', response.url)

    def test_customer_cannot_access_product_add_page(self):
        # Customers should not be able to get to the product creation form
        self.client.force_login(self.customer)
        response = self.client.get(reverse('products:add'))
        self.assertEqual(response.status_code, 302)

    def test_producer_can_access_product_add_page(self):
        # Producers should be able to reach the add product page fine
        self.client.force_login(self.producer)
        response = self.client.get(reverse('products:add'))
        self.assertEqual(response.status_code, 200)

    def test_producer_cannot_edit_another_producers_product(self):
        # A producer should only be able to edit their own products
        other_producer = User.objects.create_user(
            username='otherproducer', password='pass', role='producer'
        )
        from products.models import Product
        product = Product.objects.create(
            producer=other_producer,
            name='Their Product',
            description='Not mine',
            category='vegetables',
            price=5.00,
            stock_quantity=10,
        )
        self.client.force_login(self.producer)
        # Trying to edit another producers product should return 404
        response = self.client.get(reverse('products:edit', args=[product.pk]))
        self.assertEqual(response.status_code, 404)

    def test_logout_terminates_session(self):
        # After logging out protected pages should require re-login
        self.client.force_login(self.customer)
        self.client.get(reverse('accounts:logout'))
        response = self.client.get(reverse('marketplace'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('login', response.url)

    def test_anonymous_user_cannot_access_producer_dashboard(self):
        response = self.client.get(reverse('producer_dashboard'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('login', response.url)