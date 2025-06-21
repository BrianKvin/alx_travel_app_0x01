from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator
import uuid


class Listing(models.Model):
    """Model representing a property listing"""
    
    PROPERTY_TYPES = [
         ('apartment', 'Apartment'),
        ('house', 'House'),
        ('condo', 'Condominium'),
        ('villa', 'Villa'),
        ('cabin', 'Cabin'),
        ('loft', 'Loft'),
        ('studio', 'Studio'),
    ]
    
    listing_id = models.UUIDField(
        primary_key=True, 
        default=uuid.uuid4, 
        editable=False
    )
    host = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        related_name='listings'
    )
    title = models.CharField(max_length=200)
    description = models.TextField()
    location = models.CharField(max_length=200)
    price_per_night = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        validators=[MinValueValidator(0.01)]
    )
    property_type = models.CharField(
        max_length=20, 
        choices=PROPERTY_TYPES,
        default='apartment'
    )
    max_guests = models.PositiveIntegerField(
        validators=[MinValueValidator(1)]
    )
    bedrooms = models.PositiveIntegerField(default=1)
    bathrooms = models.PositiveIntegerField(default=1)
    amenities = models.TextField(
        help_text="Comma-separated list of amenities",
        blank=True
    )
    available = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['location']),
            models.Index(fields=['property_type']),
            models.Index(fields=['price_per_night']),
            models.Index(fields=['available']),
        ]
    
    def __str__(self):
        return f"{self.title} - {self.location}"
    
    def get_amenities_list(self):
        """Return amenities as a list"""
        if self.amenities:
            return [amenity.strip() for amenity in self.amenities.split(',')]
        return []
    
    def average_rating(self):
        """Calculate average rating from reviews"""
        reviews = self.reviews.all()
        if reviews:
            return reviews.aggregate(models.Avg('rating'))['rating__avg']
        return 0.0


class Booking(models.Model):
    """Model representing a booking for a listing"""
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('confirmed', 'Confirmed'),
        ('cancelled', 'Cancelled'),
        ('completed', 'Completed'),
    ]
    
    booking_id = models.UUIDField(
        primary_key=True, 
        default=uuid.uuid4, 
        editable=False
    )
    listing = models.ForeignKey(
        Listing, 
        on_delete=models.CASCADE, 
        related_name='bookings'
    )
    guest = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        related_name='bookings'
    )
    check_in_date = models.DateField()
    check_out_date = models.DateField()
    number_of_guests = models.PositiveIntegerField(
        validators=[MinValueValidator(1)]
    )
    total_price = models.DecimalField(
        max_digits=10, 
        decimal_places=2
    )
    status = models.CharField(
        max_length=20, 
        choices=STATUS_CHOICES,
        default='pending'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['check_in_date', 'check_out_date']),
            models.Index(fields=['status']),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(check_out_date__gt=models.F('check_in_date')),
                name='check_out_after_check_in'
            )
        ]
    
    def __str__(self):
        return f"Booking {self.booking_id} - {self.listing.title}"
    
    def clean(self):
        """Custom validation"""
        from django.core.exceptions import ValidationError
        
        if self.check_in_date and self.check_out_date:
            if self.check_out_date <= self.check_in_date:
                raise ValidationError("Check-out date must be after check-in date")
        
        if self.number_of_guests and self.listing:
            if self.number_of_guests > self.listing.max_guests:
                raise ValidationError(
                    f"Number of guests ({self.number_of_guests}) exceeds "
                    f"maximum allowed ({self.listing.max_guests})"
                )
    
    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
    
    @property
    def duration_days(self):
        """Calculate booking duration in days"""
        return (self.check_out_date - self.check_in_date).days


class Review(models.Model):
    """Model representing a review for a listing"""
    
    review_id = models.UUIDField(
        primary_key=True, 
        default=uuid.uuid4, 
        editable=False
    )
    listing = models.ForeignKey(
        Listing, 
        on_delete=models.CASCADE, 
        related_name='reviews'
    )
    guest = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        related_name='reviews'
    )
    booking = models.OneToOneField(
        Booking, 
        on_delete=models.CASCADE, 
        related_name='review',
        null=True, 
        blank=True
    )
    rating = models.PositiveIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    comment = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        unique_together = ['listing', 'guest', 'booking']
        indexes = [
            models.Index(fields=['rating']),
            models.Index(fields=['created_at']),
        ]
    
    def __str__(self):
        return f"Review by {self.guest.username} for {self.listing.title} - {self.rating}/5"