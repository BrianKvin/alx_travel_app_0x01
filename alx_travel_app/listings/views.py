from rest_framework import viewsets, status, permissions, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly
from alx_travel_app.listings import serializers
from django_filters.rest_framework import DjangoFilterBackend
from django.shortcuts import get_object_or_404
from django.contrib.auth.models import User
from django.db.models import Q, Avg
from decimal import Decimal
from .models import Listing, Booking, Review
from .serializers import (
    ListingSerializer, ListingCreateUpdateSerializer, ListingListSerializer,
    BookingSerializer, BookingCreateSerializer,
    ReviewSerializer, ReviewCreateSerializer,
    UserSerializer
)

# ============= LISTING VIEWSETS =============
class ListingViewSet(viewsets.ModelViewSet):
    """
    A ViewSet for viewing and editing listings.
    Provides list, retrieve, create, update, partial_update, and destroy actions.
    """
    queryset = Listing.objects.all()
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['property_type', 'location', 'available']
    search_fields = ['title', 'description', 'location']
    ordering_fields = ['price_per_night', 'created_at', 'bedrooms', 'max_guests']
    ordering = ['-created_at']
    lookup_field = 'listing_id'

    def get_serializer_class(self):
        if self.action in ['list', 'retrieve', 'search']:
            return ListingListSerializer
        elif self.action in ['create', 'update', 'partial_update']:
            return ListingCreateUpdateSerializer
        return ListingSerializer

    def get_permissions(self):
        if self.action in ['create']:
            self.permission_classes = [IsAuthenticated]
        elif self.action in ['update', 'partial_update', 'destroy']:
            self.permission_classes = [IsAuthenticated]
        else:
            self.permission_classes = [permissions.AllowAny]
        return super().get_permissions()

    def get_queryset(self):
        queryset = super().get_queryset()

        if self.action == 'my_listings':
            return queryset.filter(host=self.request.user)

        # Apply general listing filters for 'list' and 'search' actions
        if self.action in ['list', 'search']:
            queryset = queryset.filter(available=True)

            min_price = self.request.query_params.get('min_price')
            max_price = self.request.query_params.get('max_price')
            if min_price:
                queryset = queryset.filter(price_per_night__gte=Decimal(min_price))
            if max_price:
                queryset = queryset.filter(price_per_night__lte=Decimal(max_price))

            guests = self.request.query_params.get('guests')
            if guests:
                queryset = queryset.filter(max_guests__gte=int(guests))

            bedrooms = self.request.query_params.get('bedrooms')
            if bedrooms:
                queryset = queryset.filter(bedrooms__gte=int(bedrooms))

        if self.action in ['update', 'partial_update', 'destroy']:
            return queryset.filter(host=self.request.user)

        return queryset

    def perform_create(self, serializer):
        serializer.save(host=self.request.user)

    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated], url_path='my-listings')
    def my_listings(self, request):
        """
        List current user's listings.
        """
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], permission_classes=[permissions.AllowAny])
    def search(self, request):
        """Advanced search endpoint with multiple filters."""
        queryset = self.get_queryset() # This already applies basic filters for available listings

        # Location search
        location = request.GET.get('location')
        if location:
            queryset = queryset.filter(
                Q(location__icontains=location) | Q(title__icontains=location)
            )

        # Date availability check
        check_in = request.GET.get('check_in')
        check_out = request.GET.get('check_out')
        if check_in and check_out:
            unavailable_listings = Booking.objects.filter(
                status__in=['confirmed', 'pending'],
                check_in_date__lt=check_out,
                check_out_date__gt=check_in
            ).values_list('listing_id', flat=True)
            queryset = queryset.exclude(listing_id__in=unavailable_listings)

        # Other filters (already handled in get_queryset for general 'list' behavior, but explicitly for 'search' here)
        property_type = request.GET.get('property_type')
        if property_type:
            queryset = queryset.filter(property_type=property_type)

        # Sorting
        sort_by = request.GET.get('sort_by', 'created_at')
        if sort_by == 'price_low':
            queryset = queryset.order_by('price_per_night')
        elif sort_by == 'price_high':
            queryset = queryset.order_by('-price_per_night')
        elif sort_by == 'rating':
            queryset = queryset.annotate(avg_rating=Avg('reviews__rating')).order_by('-avg_rating')
        else:
            queryset = queryset.order_by('-created_at')

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

# ============= BOOKING VIEWSET =============
class BookingViewSet(viewsets.ModelViewSet):
    """
    A ViewSet for viewing and managing bookings.
    Provides list, retrieve, create, update, partial_update, and destroy (not explicitly for guests).
    """
    queryset = Booking.objects.all()
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['status']
    ordering_fields = ['check_in_date', 'created_at']
    ordering = ['-created_at']
    lookup_field = 'booking_id'

    def get_serializer_class(self):
        if self.action == 'create':
            return BookingCreateSerializer
        return BookingSerializer

    def get_queryset(self):
        user = self.request.user
        if self.action == 'list' or self.action == 'retrieve':
            return Booking.objects.filter(guest=user)
        elif self.action == 'host_bookings':
            return Booking.objects.filter(listing__host=user)
        elif self.action in ['update', 'partial_update']:
            # Guests can only cancel, hosts can update status
            return Booking.objects.filter(Q(guest=user) | Q(listing__host=user))
        return super().get_queryset()

    def perform_create(self, serializer):
        serializer.save(guest=self.request.user)

    def update(self, request, *args, **kwargs):
        booking = self.get_object()
        user = request.user

        # Only allow status updates
        if 'status' not in request.data:
            return Response(
                {'error': 'Only status updates are allowed'},
                status=status.HTTP_400_BAD_REQUEST
            )

        new_status = request.data.get('status')

        # Validate status transitions
        if booking.guest == user:
            # Guests can only cancel their own bookings
            if new_status != 'cancelled':
                return Response(
                    {'error': 'Guests can only cancel bookings'},
                    status=status.HTTP_403_FORBIDDEN
                )
        elif booking.listing.host == user:
            # Hosts can confirm, cancel, or mark as completed
            if new_status not in ['confirmed', 'cancelled', 'completed']:
                return Response(
                    {'error': 'Invalid status transition'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        else:
            return Response(
                {'error': 'Permission denied'},
                status=status.HTTP_403_FORBIDDEN
            )

        booking.status = new_status
        booking.save()

        serializer = self.get_serializer(booking)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated], url_path='host-bookings')
    def host_bookings(self, request):
        """
        List bookings for host's listings.
        """
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

# ============= REVIEW VIEWSET =============
class ReviewViewSet(viewsets.ModelViewSet):
    """
    A ViewSet for viewing and managing reviews.
    Provides list, retrieve, create, update, partial_update, and destroy actions.
    """
    queryset = Review.objects.all()
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ['rating', 'created_at']
    ordering = ['-created_at']
    lookup_field = 'review_id'

    def get_serializer_class(self):
        if self.action == 'create':
            return ReviewCreateSerializer
        return ReviewSerializer

    def get_permissions(self):
        if self.action in ['create']:
            self.permission_classes = [IsAuthenticated]
        elif self.action in ['update', 'partial_update', 'destroy']:
            self.permission_classes = [IsAuthenticated]
        else:
            self.permission_classes = [permissions.AllowAny]
        return super().get_permissions()

    def get_queryset(self):
        queryset = super().get_queryset()

        if self.action == 'list':
            listing_id = self.kwargs.get('listing_id')
            if listing_id:
                return queryset.filter(listing__listing_id=listing_id)
            # If listing_id is not provided for list, it will return all reviews,
            # which might not be desired for a general 'list' without a specific listing context.
            # Consider if you want a global list or only listing-specific.
            # For now, it will return all reviews if no listing_id is in kwargs.
            return queryset
        elif self.action in ['update', 'partial_update', 'destroy', 'my_reviews']:
            return queryset.filter(guest=self.request.user)
        return queryset

    def perform_create(self, serializer):
        # Ensure the review is for a completed booking
        booking_id = self.request.data.get('booking')
        if not booking_id:
            raise serializers.ValidationError({"booking": "Booking ID is required."})

        booking = get_object_or_404(Booking, booking_id=booking_id, guest=self.request.user, status='completed')
        if Review.objects.filter(booking=booking).exists():
            raise serializers.ValidationError({"booking": "A review for this booking already exists."})

        serializer.save(guest=self.request.user, listing=booking.listing)

    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated], url_path='my-reviews')
    def my_reviews(self, request):
        """
        List current user's reviews.
        """
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

# ============= UTILITY VIEWSET (Custom) =============
class UtilityViewSet(viewsets.ViewSet):
    """
    A ViewSet for various utility endpoints like dashboard statistics and property types.
    """
    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def dashboard_stats(self, request):
        """Get dashboard statistics for the current user"""
        user = request.user

        # Guest stats
        guest_bookings = Booking.objects.filter(guest=user)
        guest_stats = {
            'total_bookings': guest_bookings.count(),
            'confirmed_bookings': guest_bookings.filter(status='confirmed').count(),
            'completed_bookings': guest_bookings.filter(status='completed').count(),
            'cancelled_bookings': guest_bookings.filter(status='cancelled').count(),
            'total_reviews_given': Review.objects.filter(guest=user).count(),
        }

        # Host stats
        host_listings = Listing.objects.filter(host=user)
        host_bookings = Booking.objects.filter(listing__host=user)
        host_stats = {
            'total_listings': host_listings.count(),
            'active_listings': host_listings.filter(available=True).count(),
            'total_bookings_received': host_bookings.count(),
            'confirmed_bookings_received': host_bookings.filter(status='confirmed').count(),
            'total_reviews_received': Review.objects.filter(listing__host=user).count(),
            'average_rating': Review.objects.filter(listing__host=user).aggregate(
                avg_rating=Avg('rating')
            )['avg_rating'] or 0.0
        }

        return Response({
            'guest_stats': guest_stats,
            'host_stats': host_stats
        })

    @action(detail=False, methods=['get'], permission_classes=[permissions.AllowAny])
    def property_types(self, request):
        """Get available property types"""
        return Response([
            {'value': choice[0], 'label': choice[1]}
            for choice in Listing.PROPERTY_TYPES
        ])















































# # ============= LISTING VIEWS =============

# class ListingListView(generics.ListAPIView):
#     """List all available listings with filtering and search"""
    
#     serializer_class = ListingListSerializer
#     permission_classes = [permissions.AllowAny]
#     filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
#     filterset_fields = ['property_type', 'location', 'available']
#     search_fields = ['title', 'description', 'location']
#     ordering_fields = ['price_per_night', 'created_at', 'bedrooms', 'max_guests']
#     ordering = ['-created_at']
    
#     def get_queryset(self):
#         queryset = Listing.objects.filter(available=True)
        
#         # Price range filtering
#         min_price = self.request.query_params.get('min_price')
#         max_price = self.request.query_params.get('max_price')
        
#         if min_price:
#             queryset = queryset.filter(price_per_night__gte=Decimal(min_price))
#         if max_price:
#             queryset = queryset.filter(price_per_night__lte=Decimal(max_price))
        
#         # Guest capacity filtering
#         guests = self.request.query_params.get('guests')
#         if guests:
#             queryset = queryset.filter(max_guests__gte=int(guests))
        
#         # Bedrooms filtering
#         bedrooms = self.request.query_params.get('bedrooms')
#         if bedrooms:
#             queryset = queryset.filter(bedrooms__gte=int(bedrooms))
        
#         return queryset


# class ListingDetailView(generics.RetrieveAPIView):
#     """Retrieve a single listing by ID"""
    
#     queryset = Listing.objects.all()
#     serializer_class = ListingSerializer
#     permission_classes = [permissions.AllowAny]
#     lookup_field = 'listing_id'


# class ListingCreateView(generics.CreateAPIView):
#     """Create a new listing (host only)"""
    
#     serializer_class = ListingCreateUpdateSerializer
#     permission_classes = [IsAuthenticated]
    
#     def perform_create(self, serializer):
#         serializer.save(host=self.request.user)


# class ListingUpdateView(generics.UpdateAPIView):
#     """Update a listing (owner only)"""
    
#     serializer_class = ListingCreateUpdateSerializer
#     permission_classes = [IsAuthenticated]
#     lookup_field = 'listing_id'
    
#     def get_queryset(self):
#         return Listing.objects.filter(host=self.request.user)


# class ListingDeleteView(generics.DestroyAPIView):
#     """Delete a listing (owner only)"""
    
#     permission_classes = [IsAuthenticated]
#     lookup_field = 'listing_id'
    
#     def get_queryset(self):
#         return Listing.objects.filter(host=self.request.user)


# class MyListingsView(generics.ListAPIView):
#     """List current user's listings"""
    
#     serializer_class = ListingSerializer
#     permission_classes = [IsAuthenticated]
    
#     def get_queryset(self):
#         return Listing.objects.filter(host=self.request.user)


# # ============= BOOKING VIEWS =============

# class BookingCreateView(generics.CreateAPIView):
#     """Create a new booking"""
    
#     serializer_class = BookingCreateSerializer
#     permission_classes = [IsAuthenticated]


# class BookingListView(generics.ListAPIView):
#     """List user's bookings"""
    
#     serializer_class = BookingSerializer
#     permission_classes = [IsAuthenticated]
#     filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
#     filterset_fields = ['status']
#     ordering_fields = ['check_in_date', 'created_at']
#     ordering = ['-created_at']
    
#     def get_queryset(self):
#         return Booking.objects.filter(guest=self.request.user)


# class BookingDetailView(generics.RetrieveAPIView):
#     """Retrieve a single booking"""
    
#     serializer_class = BookingSerializer
#     permission_classes = [IsAuthenticated]
#     lookup_field = 'booking_id'
    
#     def get_queryset(self):
#         return Booking.objects.filter(guest=self.request.user)


# class BookingUpdateView(generics.UpdateAPIView):
#     """Update booking status (limited fields)"""
    
#     serializer_class = BookingSerializer
#     permission_classes = [IsAuthenticated]
#     lookup_field = 'booking_id'
    
#     def get_queryset(self):
#         # Guests can only cancel, hosts can update status
#         user = self.request.user
#         return Booking.objects.filter(
#             Q(guest=user) | Q(listing__host=user)
#         )
    
#     def update(self, request, *args, **kwargs):
#         booking = self.get_object()
        
#         # Only allow status updates
#         if 'status' not in request.data:
#             return Response(
#                 {'error': 'Only status updates are allowed'},
#                 status=status.HTTP_400_BAD_REQUEST
#             )
        
#         new_status = request.data.get('status')
        
#         # Validate status transitions
#         if booking.guest == request.user:
#             # Guests can only cancel their own bookings
#             if new_status != 'cancelled':
#                 return Response(
#                     {'error': 'Guests can only cancel bookings'},
#                     status=status.HTTP_403_FORBIDDEN
#                 )
#         elif booking.listing.host == request.user:
#             # Hosts can confirm or cancel bookings
#             if new_status not in ['confirmed', 'cancelled', 'completed']:
#                 return Response(
#                     {'error': 'Invalid status transition'},
#                     status=status.HTTP_400_BAD_REQUEST
#                 )
#         else:
#             return Response(
#                 {'error': 'Permission denied'},
#                 status=status.HTTP_403_FORBIDDEN
#             )
        
#         booking.status = new_status
#         booking.save()
        
#         serializer = self.get_serializer(booking)
#         return Response(serializer.data)


# class HostBookingsView(generics.ListAPIView):
#     """List bookings for host's listings"""
    
#     serializer_class = BookingSerializer
#     permission_classes = [IsAuthenticated]
#     filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
#     filterset_fields = ['status']
#     ordering_fields = ['check_in_date', 'created_at']
#     ordering = ['-created_at']
    
#     def get_queryset(self):
#         return Booking.objects.filter(listing__host=self.request.user)


# # ============= REVIEW VIEWS =============

# class ReviewCreateView(generics.CreateAPIView):
#     """Create a review for a completed booking"""
    
#     serializer_class = ReviewCreateSerializer
#     permission_classes = [IsAuthenticated]


# class ReviewListView(generics.ListAPIView):
#     """List reviews for a specific listing"""
    
#     serializer_class = ReviewSerializer
#     permission_classes = [permissions.AllowAny]
#     filter_backends = [filters.OrderingFilter]
#     ordering_fields = ['rating', 'created_at']
#     ordering = ['-created_at']
    
#     def get_queryset(self):
#         listing_id = self.kwargs.get('listing_id')
#         return Review.objects.filter(listing__listing_id=listing_id)


# class ReviewDetailView(generics.RetrieveAPIView):
#     """Retrieve a single review"""
    
#     serializer_class = ReviewSerializer
#     permission_classes = [permissions.AllowAny]
#     lookup_field = 'review_id'
#     queryset = Review.objects.all()


# class ReviewUpdateView(generics.UpdateAPIView):
#     """Update a review (author only)"""
    
#     serializer_class = ReviewCreateSerializer
#     permission_classes = [IsAuthenticated]
#     lookup_field = 'review_id'
    
#     def get_queryset(self):
#         return Review.objects.filter(guest=self.request.user)


# class ReviewDeleteView(generics.DestroyAPIView):
#     """Delete a review (author only)"""
    
#     permission_classes = [IsAuthenticated]
#     lookup_field = 'review_id'
    
#     def get_queryset(self):
#         return Review.objects.filter(guest=self.request.user)


# class MyReviewsView(generics.ListAPIView):
#     """List current user's reviews"""
    
#     serializer_class = ReviewSerializer
#     permission_classes = [IsAuthenticated]
    
#     def get_queryset(self):
#         return Review.objects.filter(guest=self.request.user)


# # ============= UTILITY VIEWS =============

# @api_view(['GET'])
# @permission_classes([permissions.AllowAny])
# def search_listings(request):
#     """Advanced search endpoint with multiple filters"""
    
#     queryset = Listing.objects.filter(available=True)
    
#     # Location search
#     location = request.GET.get('location')
#     if location:
#         queryset = queryset.filter(
#             Q(location__icontains=location) | Q(title__icontains=location)
#         )
    
#     # Date availability check
#     check_in = request.GET.get('check_in')
#     check_out = request.GET.get('check_out')
    
#     if check_in and check_out:
#         # Exclude listings with overlapping bookings
#         unavailable_listings = Booking.objects.filter(
#             status__in=['confirmed', 'pending'],
#             check_in_date__lt=check_out,
#             check_out_date__gt=check_in
#         ).values_list('listing_id', flat=True)
        
#         queryset = queryset.exclude(listing_id__in=unavailable_listings)
    
#     # Other filters
#     property_type = request.GET.get('property_type')
#     if property_type:
#         queryset = queryset.filter(property_type=property_type)
    
#     min_price = request.GET.get('min_price')
#     max_price = request.GET.get('max_price')
#     if min_price:
#         queryset = queryset.filter(price_per_night__gte=Decimal(min_price))
#     if max_price:
#         queryset = queryset.filter(price_per_night__lte=Decimal(max_price))
    
#     guests = request.GET.get('guests')
#     if guests:
#         queryset = queryset.filter(max_guests__gte=int(guests))
    
#     # Sorting
#     sort_by = request.GET.get('sort_by', 'created_at')
#     if sort_by == 'price_low':
#         queryset = queryset.order_by('price_per_night')
#     elif sort_by == 'price_high':
#         queryset = queryset.order_by('-price_per_night')
#     elif sort_by == 'rating':
#         queryset = queryset.annotate(avg_rating=Avg('reviews__rating')).order_by('-avg_rating')
#     else:
#         queryset = queryset.order_by('-created_at')
    
#     serializer = ListingListSerializer(queryset, many=True)
#     return Response(serializer.data)


# @api_view(['GET'])
# @permission_classes([IsAuthenticated])
# def dashboard_stats(request):
#     """Get dashboard statistics for the current user"""
    
#     user = request.user
    
#     # Guest stats
#     guest_bookings = Booking.objects.filter(guest=user)
#     guest_stats = {
#         'total_bookings': guest_bookings.count(),
#         'confirmed_bookings': guest_bookings.filter(status='confirmed').count(),
#         'completed_bookings': guest_bookings.filter(status='completed').count(),
#         'cancelled_bookings': guest_bookings.filter(status='cancelled').count(),
#         'total_reviews_given': Review.objects.filter(guest=user).count(),
#     }
    
#     # Host stats
#     host_listings = Listing.objects.filter(host=user)
#     host_bookings = Booking.objects.filter(listing__host=user)
#     host_stats = {
#         'total_listings': host_listings.count(),
#         'active_listings': host_listings.filter(available=True).count(),
#         'total_bookings_received': host_bookings.count(),
#         'confirmed_bookings_received': host_bookings.filter(status='confirmed').count(),
#         'total_reviews_received': Review.objects.filter(listing__host=user).count(),
#         'average_rating': Review.objects.filter(listing__host=user).aggregate(
#             avg_rating=Avg('rating')
#         )['avg_rating'] or 0.0
#     }
    
#     return Response({
#         'guest_stats': guest_stats,
#         'host_stats': host_stats
#     })


# @api_view(['GET'])
# @permission_classes([permissions.AllowAny])
# def property_types(request):
#     """Get available property types"""
    
#     return Response([
#         {'value': choice[0], 'label': choice[1]}
#         for choice in Listing.PROPERTY_TYPES
#     ])