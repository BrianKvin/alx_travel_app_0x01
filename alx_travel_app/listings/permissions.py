from rest_framework import permissions


class IsOwnerOrReadOnly(permissions.BasePermission):
    """
    Custom permission to only allow owners of an object to edit it.
    """

    def has_object_permission(self, request, view, obj):
        # Read permissions are allowed for any request,
        # so we'll always allow GET, HEAD or OPTIONS requests.
        if request.method in permissions.SAFE_METHODS:
            return True

        # Check if the object has a 'host' attribute (for Listing)
        if hasattr(obj, 'host'):
            return obj.host == request.user
        
        # Check if the object has a 'guest' attribute (for Booking, Review)
        if hasattr(obj, 'guest'):
            return obj.guest == request.user
        
        # Fallback to user attribute
        if hasattr(obj, 'user'):
            return obj.user == request.user

        return False


class IsHostOrReadOnly(permissions.BasePermission):
    """
    Custom permission to only allow hosts to edit their listings.
    """

    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True

        return obj.host == request.user


class IsGuestOrHost(permissions.BasePermission):
    """
    Custom permission for bookings - guests and hosts can view/edit.
    """

    def has_object_permission(self, request, view, obj):
        # Allow both guest and host to access the booking
        return obj.guest == request.user or obj.listing.host == request.user


class IsGuestOnly(permissions.BasePermission):
    """
    Custom permission to only allow guests to edit their own bookings/reviews.
    """

    def has_object_permission(self, request, view, obj):
        return obj.guest == request.user


class CanReviewBooking(permissions.BasePermission):
    """
    Custom permission to check if a user can review a booking.
    """

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        
        # For POST requests, check if user can create a review
        if request.method == 'POST':
            booking_id = request.data.get('booking_id')
            if not booking_id:
                return False
            
            try:
                from .models import Booking
                booking = Booking.objects.get(booking_id=booking_id)
                
                # User must be the guest of the booking
                if booking.guest != request.user:
                    return False
                
                # Booking must be completed
                if booking.status != 'completed':
                    return False
                
                # Check if review already exists
                if hasattr(booking, 'review'):
                    return False
                
                return True
            except Booking.DoesNotExist:
                return False
        
        return True