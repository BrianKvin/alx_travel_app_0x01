from django.db import models
from django.contrib.auth.models import User
import uuid

class Listing(models.Model):
    """Existing Listing model - add this if not present"""
    title = models.CharField(max_length=255)
    description = models.TextField()
    price_per_night = models.DecimalField(max_digits=10, decimal_places=2)
    location = models.CharField(max_length=255)
    host = models.ForeignKey(User, on_delete=models.CASCADE, related_name='listings')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

class Booking(models.Model):
    """Existing Booking model - add this if not present"""
    BOOKING_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('confirmed', 'Confirmed'),
        ('cancelled', 'Cancelled'),
        ('completed', 'Completed'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    listing = models.ForeignKey(Listing, on_delete=models.CASCADE, related_name='bookings')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='bookings')
    check_in_date = models.DateField()
    check_out_date = models.DateField()
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=BOOKING_STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Booking {self.id} - {self.listing.title}"

class Payment(models.Model):
    """Payment model for handling Chapa payment transactions"""
    PAYMENT_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
        ('refunded', 'Refunded'),
    ]
    
    PAYMENT_METHOD_CHOICES = [
        ('telebirr', 'Telebirr'),
        ('cbe', 'CBE'),
        ('ebirr', 'eBirr'),
        ('mpesa', 'M-Pesa'),
        ('card', 'Card'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    booking = models.OneToOneField(Booking, on_delete=models.CASCADE, related_name='payment')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='payments')
    
    # Payment details
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='ETB')
    
    # Chapa transaction details
    transaction_id = models.CharField(max_length=255, unique=True, null=True, blank=True)
    checkout_url = models.URLField(null=True, blank=True)
    reference = models.CharField(max_length=255, unique=True)
    
    # Payment status and method
    status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default='pending')
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES, null=True, blank=True)
    
    # Timestamps
    initiated_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Additional Chapa response data
    chapa_response = models.JSONField(null=True, blank=True)
    webhook_data = models.JSONField(null=True, blank=True)
    
    # Metadata
    metadata = models.JSONField(null=True, blank=True)
    
    class Meta:
        ordering = ['-initiated_at']
        
    def __str__(self):
        return f"Payment {self.reference} - {self.amount} {self.currency}"
    
    def save(self, *args, **kwargs):
        if not self.reference:
            # Generate unique reference
            self.reference = f"ALX_TRAVEL_{uuid.uuid4().hex[:8].upper()}"
        super().save(*args, **kwargs)