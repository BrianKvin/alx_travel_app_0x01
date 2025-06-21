from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

# Create a router and register our viewsets with it
router = DefaultRouter()
router.register(r'listings', views.ListingViewSet, basename='listing')
router.register(r'bookings', views.BookingViewSet, basename='booking')
router.register(r'reviews', views.ReviewViewSet, basename='review')
router.register(r'dashboard', views.DashboardViewSet, basename='dashboard')

# The API URLs are now determined automatically by the router
urlpatterns = [
    path('api/', include(router.urls)),
]

# Available endpoints with ViewSets:
# 
# LISTINGS:
# GET    /api/listings/                    - List all available listings
# POST   /api/listings/                    - Create a new listing
# GET    /api/listings/{listing_id}/       - Retrieve a specific listing
# PUT    /api/listings/{listing_id}/       - Update a listing (full)
# PATCH  /api/listings/{listing_id}/       - Update a listing (partial)
# DELETE /api/listings/{listing_id}/       - Delete a listing
# GET    /api/listings/my-listings/        - List current user's listings
# GET    /api/listings/search/             - Advanced search with filters
# GET    /api/listings/property-types/     - Get available property types
#
# BOOKINGS:
# GET    /api/bookings/                    - List user's bookings
# POST   /api/bookings/                    - Create a new booking
# GET    /api/bookings/{booking_id}/       - Retrieve a specific booking
# PUT    /api/bookings/{booking_id}/       - Update booking status
# PATCH  /api/bookings/{booking_id}/       - Update booking status (partial)
# DELETE /api/bookings/{booking_id}/       - Delete a booking
# GET    /api/bookings/host-bookings/      - List bookings for host's listings
#
# REVIEWS:
# GET    /api/reviews/                     - List all reviews
# POST   /api/reviews/                     - Create a new review
# GET    /api/reviews/{review_id}/         - Retrieve a specific review
# PUT    /api/reviews/{review_id}/         - Update a review (full)
# PATCH  /api/reviews/{review_id}/         - Update a review (partial)
# DELETE /api/reviews/{review_id}/         - Delete a review
# GET    /api/reviews/my-reviews/          - List current user's reviews
# GET    /api/reviews/listing/{listing_id}/ - List reviews for a specific listing
#
# DASHBOARD:
# GET    /api/dashboard/stats/             - Get dashboard statistics