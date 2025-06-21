import django_filters
from django.db.models import Q, Avg
from .models import Listing, Booking, Review
from decimal import Decimal


class ListingFilter(django_filters.FilterSet):
    """Advanced filtering for listings"""
    
    # Price range filters
    min_price = django_filters.NumberFilter(field_name='price_per_night', lookup_expr='gte')
    max_price = django_filters.NumberFilter(field_name='price_per_night', lookup_expr='lte')
    
    # Capacity filters
    min_guests = django_filters.NumberFilter(field_name='max_guests', lookup_expr='gte')
    min_bedrooms = django_filters.NumberFilter(field_name='bedrooms', lookup_expr='gte')
    min_bathrooms = django_filters.NumberFilter(field_name='bathrooms', lookup_expr='gte')
    
    # Location search
    location = django_filters.CharFilter(method='filter_location')
    
    # Amenities search
    amenities = django_filters.CharFilter(method='filter_amenities')
    
    # Rating filter
    min_rating = django_filters.NumberFilter(method='filter_min_rating')
    
    # Date availability filter
    available_from = django_filters.DateFilter(method='filter_available_dates')
    available_to = django_filters.DateFilter(method='filter_available_dates')
    
    class Meta:
        model = Listing
        fields = {
            'property_type': ['exact', 'in'],
            'available': ['exact'],
            'max_guests': ['exact', 'gte', 'lte'],
            'bedrooms': ['exact', 'gte', 'lte'],
            'bathrooms': ['exact', 'gte', 'lte'],
        }
    
    def filter_location(self, queryset, name, value):
        """Filter by location (case-insensitive, partial match)"""
        return queryset.filter(
            Q(location__icontains=value) | Q(title__icontains=value)
        )
    
    def filter_amenities(self, queryset, name, value):
        """Filter by amenities (comma-separated list)"""
        amenities_list = [amenity.strip().lower() for amenity in value.split(',')]
        q_objects = Q()
        
        for amenity in amenities_list:
            q_objects |= Q(amenities__icontains=amenity)
        
        return queryset.filter(q_objects)
    
    def filter_min_rating(self, queryset, name, value):
        """Filter by minimum average rating"""
        return queryset.annotate(
            avg_rating=Avg('reviews__rating')
        ).filter(avg_rating__gte=value)
    
    def filter_available_dates(self, queryset, name, value):
        """Filter listings available for specific date range"""
        # This is a simplified version - you might want to implement more complex logic
        # based on your booking system requirements
        
        check_in = self.data.get('available_from')
        check_out = self.data.get('available_to')
        
        if check_in and check_out:
            # Exclude listings with overlapping confirmed/pending bookings
            unavailable_listings = Booking.objects.filter(
                status__in=['confirmed', 'pending'],
                check_in_date__lt=check_out,
                check_out_date__gt=check_in
            ).values_list('listing_id', flat=True)
            
            return queryset.exclude(listing_id__in=unavailable_listings)
        
        return queryset


class BookingFilter(django_filters.FilterSet):
    """Filtering for bookings"""
    
    # Date range filters
    check_in_after = django_filters.DateFilter(field_name='check_in_date', lookup_expr='gte')
    check_in_before = django_filters.DateFilter(field_name='check_in_date', lookup_expr='lte')
    check_out_after = django_filters.DateFilter(field_name='check_out_date', lookup_expr='gte')
    check_out_before = django_filters.DateFilter(field_name='check_out_date', lookup_expr='lte')
    
    # Price range filters
    min_total = django_filters.NumberFilter(field_name='total_price', lookup_expr='gte')
    max_total = django_filters.NumberFilter(field_name='total_price', lookup_expr='lte')
    
    # Duration filters
    min_duration = django_filters.NumberFilter(method='filter_min_duration')
    max_duration = django_filters.NumberFilter(method='filter_max_duration')
    
    # Listing filters
    property_type = django_filters.CharFilter(field_name='listing__property_type')
    location = django_filters.CharFilter(field_name='listing__location', lookup_expr='icontains')
    
    class Meta:
        model = Booking
        fields = {
            'status': ['exact', 'in'],
            'number_of_guests': ['exact', 'gte', 'lte'],
        }
    
    def filter_min_duration(self, queryset, name, value):
        """Filter bookings by minimum duration in days"""
        from django.db.models import F, IntegerField
        from django.db.models.functions import Extract
        
        return queryset.annotate(
            duration=Extract('check_out_date', 'day') - Extract('check_in_date', 'day')
        ).filter(duration__gte=value)
    
    def filter_max_duration(self, queryset, name, value):
        """Filter bookings by maximum duration in days"""
        from django.db.models import F, IntegerField
        from django.db.models.functions import Extract
        
        return queryset.annotate(
            duration=Extract('check_out_date', 'day') - Extract('check_in_date', 'day')
        ).filter(duration__lte=value)


class ReviewFilter(django_filters.FilterSet):
    """Filtering for reviews"""
    
    # Rating filters
    min_rating = django_filters.NumberFilter(field_name='rating', lookup_expr='gte')
    max_rating = django_filters.NumberFilter(field_name='rating', lookup_expr='lte')
    
    # Date filters
    created_after = django_filters.DateFilter(field_name='created_at', lookup_expr='gte')
    created_before = django_filters.DateFilter(field_name='created_at', lookup_expr='lte')
    
    # Text search in comments
    comment_contains = django_filters.CharFilter(field_name='comment', lookup_expr='icontains')
    
    # Listing filters
    property_type = django_filters.CharFilter(field_name='listing__property_type')
    location = django_filters.CharFilter(field_name='listing__location', lookup_expr='icontains')
    
    class Meta:
        model = Review
        fields = {
            'rating': ['exact', 'gte', 'lte'],
        }