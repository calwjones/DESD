from django.test import TestCase
from django.utils import timezone
from django.core.exceptions import ValidationError
from datetime import timedelta
from .forms import CheckoutForm
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