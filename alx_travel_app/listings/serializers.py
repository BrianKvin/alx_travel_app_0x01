from rest_framework import serializers
from django.contrib.auth.models import User
from .models import Listing, Booking, Review
from django.db import models
from datetime import date


class UserSerializer(serializers.ModelSerializer):
    """Serializer for User model"""
    
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'date_joined']
        read_only_fields = ['id', 'date_joined']


class ListingSerializer(serializers.ModelSerializer):
    """Serializer for Listing model"""
    
    host = UserSerializer(read_only=True)
    amenities_list = serializers.SerializerMethodField()
    average_rating = serializers.SerializerMethodField()
    total_reviews = serializers.SerializerMethodField()
    
    class Meta:
        model = Listing
        fields = [
            'listing_id', 'host', 'title', 'description', 'location',
            'price_per_night', 'property_type', 'max_guests', 'bedrooms',
            'bathrooms', 'amenities', 'amenities_list', 'available',
            'average_rating', 'total_reviews', 'created_at', 'updated_at'
        ]
        read_only_fields = ['listing_id', 'created_at', 'updated_at']
    
    def get_amenities_list(self, obj):
        return obj.get_amenities_list()
    
    def get_average_rating(self, obj):
        return round(obj.average_rating(), 2) if obj.average_rating() else 0.0
    
    def get_total_reviews(self, obj):
        return obj.reviews.count()
    
    def create(self, validated_data):
        # Set the host to the current user
        validated_data['host'] = self.context['request'].user
        return super().create(validated_data)


class ListingCreateUpdateSerializer(serializers.ModelSerializer):
    """Serializer for creating/updating listings"""
    
    class Meta:
        model = Listing
        fields = [
            'title', 'description', 'location', 'price_per_night',
            'property_type', 'max_guests', 'bedrooms', 'bathrooms',
            'amenities', 'available'
        ]


class BookingSerializer(serializers.ModelSerializer):
    """Serializer for Booking model"""
    
    listing = ListingSerializer(read_only=True)
    guest = UserSerializer(read_only=True)
    duration_days = serializers.ReadOnlyField()
    
    class Meta:
        model = Booking
        fields = [
            'booking_id', 'listing', 'guest', 'check_in_date',
            'check_out_date', 'number_of_guests', 'total_price',
            'status', 'duration_days', 'created_at', 'updated_at'
        ]
        read_only_fields = ['booking_id', 'created_at', 'updated_at']


class BookingCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating bookings"""
    
    listing_id = serializers.UUIDField()
    
    class Meta:
        model = Booking
        fields = [
            'listing_id', 'check_in_date', 'check_out_date',
            'number_of_guests'
        ]
    
    def validate(self, data):
        """Custom validation for booking creation"""
        
        # Check if check-out is after check-in
        if data['check_out_date'] <= data['check_in_date']:
            raise serializers.ValidationError(
                "Check-out date must be after check-in date"
            )
        
        # Check if dates are not in the past
        if data['check_in_date'] < date.today():
            raise serializers.ValidationError(
                "Check-in date cannot be in the past"
            )
        
        # Validate listing exists and is available
        try:
            listing = Listing.objects.get(listing_id=data['listing_id'])
            if not listing.available:
                raise serializers.ValidationError("This listing is not available")
        except Listing.DoesNotExist:
            raise serializers.ValidationError("Listing not found")
        
        # Check guest capacity
        if data['number_of_guests'] > listing.max_guests:
            raise serializers.ValidationError(
                f"Number of guests ({data['number_of_guests']}) exceeds "
                f"maximum allowed ({listing.max_guests})"
            )
        
        # Check for overlapping bookings
        overlapping_bookings = Booking.objects.filter(
            listing=listing,
            status__in=['confirmed', 'pending'],
            check_in_date__lt=data['check_out_date'],
            check_out_date__gt=data['check_in_date']
        )
        
        if overlapping_bookings.exists():
            raise serializers.ValidationError(
                "The listing is not available for the selected dates"
            )
        
        return data
    
    def create(self, validated_data):
        """Create booking with calculated total price"""
        
        listing_id = validated_data.pop('listing_id')
        listing = Listing.objects.get(listing_id=listing_id)
        
        # Calculate total price
        duration = (validated_data['check_out_date'] - validated_data['check_in_date']).days
        total_price = listing.price_per_night * duration
        
        booking = Booking.objects.create(
            listing=listing,
            guest=self.context['request'].user,
            total_price=total_price,
            **validated_data
        )
        
        return booking


class ReviewSerializer(serializers.ModelSerializer):
    """Serializer for Review model"""
    
    guest = UserSerializer(read_only=True)
    listing = ListingSerializer(read_only=True)
    
    class Meta:
        model = Review
        fields = [
            'review_id', 'listing', 'guest', 'booking', 'rating',
            'comment', 'created_at', 'updated_at'
        ]
        read_only_fields = ['review_id', 'created_at', 'updated_at']


class ReviewCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating reviews"""
    
    booking_id = serializers.UUIDField()
    
    class Meta:
        model = Review
        fields = ['booking_id', 'rating', 'comment']
    
    def validate(self, data):
        """Custom validation for review creation"""
        
        try:
            booking = Booking.objects.get(booking_id=data['booking_id'])
        except Booking.DoesNotExist:
            raise serializers.ValidationError("Booking not found")
        
        # Check if booking belongs to the current user
        if booking.guest != self.context['request'].user:
            raise serializers.ValidationError(
                "You can only review your own bookings"
            )
        
        # Check if booking is completed
        if booking.status != 'completed':
            raise serializers.ValidationError(
                "You can only review completed bookings"
            )
        
        # Check if review already exists
        if hasattr(booking, 'review'):
            raise serializers.ValidationError(
                "You have already reviewed this booking"
            )
        
        return data
    
    def create(self, validated_data):
        """Create review"""
        
        booking_id = validated_data.pop('booking_id')
        booking = Booking.objects.get(booking_id=booking_id)
        
        review = Review.objects.create(
            listing=booking.listing,
            guest=self.context['request'].user,
            booking=booking,
            **validated_data
        )
        
        return review


class ListingListSerializer(serializers.ModelSerializer):
    """Simplified serializer for listing lists"""
    
    average_rating = serializers.SerializerMethodField()
    total_reviews = serializers.SerializerMethodField()
    
    class Meta:
        model = Listing
        fields = [
            'listing_id', 'title', 'location', 'price_per_night',
            'property_type', 'max_guests', 'bedrooms', 'bathrooms',
            'average_rating', 'total_reviews', 'available'
        ]
    
    def get_average_rating(self, obj):
        return round(obj.average_rating(), 2) if obj.average_rating() else 0.0
    
    def get_total_reviews(self, obj):
        return obj.reviews.count()