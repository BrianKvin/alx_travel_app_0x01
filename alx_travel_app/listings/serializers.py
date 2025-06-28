from rest_framework import serializers
from .models import Payment, Booking, Listing

class PaymentSerializer(serializers.ModelSerializer):
    """Serializer for Payment model"""
    booking_details = serializers.SerializerMethodField()
    
    class Meta:
        model = Payment
        fields = [
            'id', 'booking', 'booking_details', 'user', 'amount', 'currency',
            'transaction_id', 'reference', 'status', 'payment_method',
            'initiated_at', 'completed_at', 'updated_at', 'metadata'
        ]
        read_only_fields = [
            'id', 'transaction_id', 'reference', 'initiated_at', 
            'completed_at', 'updated_at'
        ]
    
    def get_booking_details(self, obj):
        return {
            'id': str(obj.booking.id),
            'listing_title': obj.booking.listing.title,
            'check_in_date': obj.booking.check_in_date,
            'check_out_date': obj.booking.check_out_date,
            'total_amount': obj.booking.total_amount,
            'status': obj.booking.status
        }

class PaymentInitiationSerializer(serializers.Serializer):
    """Serializer for payment initiation request"""
    booking_id = serializers.UUIDField()
    phone_number = serializers.CharField(max_length=15, required=False)
    return_url = serializers.URLField(required=False)
    cancel_url = serializers.URLField(required=False)

class PaymentStatusSerializer(serializers.ModelSerializer):
    """Simplified serializer for payment status"""
    booking_id = serializers.UUIDField(source='booking.id', read_only=True)
    listing_title = serializers.CharField(source='booking.listing.title', read_only=True)
    
    class Meta:
        model = Payment
        fields = [
            'id', 'booking_id', 'listing_title', 'amount', 'currency',
            'reference', 'status', 'payment_method', 'initiated_at', 'completed_at'
        ]