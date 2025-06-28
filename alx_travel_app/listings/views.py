import os
import requests
import json
import logging
from decimal import Decimal
from datetime import datetime
from django.conf import settings
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.core.mail import send_mail
from django.template.loader import render_to_string
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from celery import shared_task
from .models import Booking, Payment, Listing
from .serializers import PaymentSerializer, BookingSerializer

logger = logging.getLogger(__name__)

# Chapa API Configuration
CHAPA_BASE_URL = "https://api.chapa.co/v1"
CHAPA_SECRET_KEY = os.getenv('CHAPA_SECRET_KEY')

if not CHAPA_SECRET_KEY:
    logger.error("CHAPA_SECRET_KEY environment variable not set")

class ChapaAPI:
    """Chapa API wrapper for payment operations"""
    
    def __init__(self):
        self.base_url = CHAPA_BASE_URL
        self.secret_key = CHAPA_SECRET_KEY
        self.headers = {
            'Authorization': f'Bearer {self.secret_key}',
            'Content-Type': 'application/json'
        }
    
    def initialize_payment(self, payment_data):
        """Initialize payment with Chapa API"""
        url = f"{self.base_url}/transaction/initialize"
        
        try:
            response = requests.post(url, headers=self.headers, json=payment_data)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Chapa payment initialization error: {str(e)}")
            return None
    
    def verify_payment(self, transaction_id):
        """Verify payment status with Chapa API"""
        url = f"{self.base_url}/transaction/verify/{transaction_id}"
        
        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Chapa payment verification error: {str(e)}")
            return None

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def initiate_payment(request):
    """
    Initiate payment for a booking
    """
    try:
        booking_id = request.data.get('booking_id')
        return_url = request.data.get('return_url', 'http://localhost:3000/payment/success')
        cancel_url = request.data.get('cancel_url', 'http://localhost:3000/payment/cancel')
        
        if not booking_id:
            return Response(
                {'error': 'booking_id is required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get booking
        booking = get_object_or_404(Booking, id=booking_id, user=request.user)
        
        # Check if payment already exists
        if hasattr(booking, 'payment') and booking.payment.status in ['completed', 'processing']:
            return Response(
                {'error': 'Payment already exists for this booking'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Create or get payment record
        payment, created = Payment.objects.get_or_create(
            booking=booking,
            defaults={
                'user': request.user,
                'amount': booking.total_amount,
                'currency': 'ETB',
                'status': 'pending'
            }
        )
        
        # Prepare Chapa payment data
        chapa_data = {
            'amount': str(payment.amount),
            'currency': payment.currency,
            'email': request.user.email,
            'first_name': request.user.first_name or 'Guest',
            'last_name': request.user.last_name or 'User',
            'phone_number': request.data.get('phone_number', ''),
            'tx_ref': payment.reference,
            'callback_url': f"{request.build_absolute_uri('/api/payments/webhook/')}",
            'return_url': return_url,
            'customization': {
                'title': f'ALX Travel - {booking.listing.title}',
                'description': f'Payment for booking from {booking.check_in_date} to {booking.check_out_date}',
                'logo': 'https://your-logo-url.com/logo.png'
            },
            'metadata': {
                'booking_id': str(booking.id),
                'user_id': str(request.user.id),
                'listing_title': booking.listing.title
            }
        }
        
        # Initialize payment with Chapa
        chapa_api = ChapaAPI()
        chapa_response = chapa_api.initialize_payment(chapa_data)
        
        if not chapa_response:
            return Response(
                {'error': 'Failed to initialize payment with Chapa'}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
        # Update payment record
        if chapa_response.get('status') == 'success':
            payment.checkout_url = chapa_response['data']['checkout_url']
            payment.chapa_response = chapa_response
            payment.status = 'processing'
            payment.save()
            
            # Update booking status
            booking.status = 'pending'
            booking.save()
            
            return Response({
                'success': True,
                'payment_id': str(payment.id),
                'checkout_url': payment.checkout_url,
                'reference': payment.reference,
                'amount': payment.amount,
                'currency': payment.currency
            })
        else:
            payment.status = 'failed'
            payment.chapa_response = chapa_response
            payment.save()
            
            return Response(
                {'error': 'Payment initialization failed', 'details': chapa_response}, 
                status=status.HTTP_400_BAD_REQUEST
            )
            
    except Exception as e:
        logger.error(f"Payment initiation error: {str(e)}")
        return Response(
            {'error': 'Internal server error'}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def verify_payment(request, reference):
    """
    Verify payment status
    """
    try:
        payment = get_object_or_404(Payment, reference=reference, user=request.user)
        
        # Verify with Chapa API
        chapa_api = ChapaAPI()
        chapa_response = chapa_api.verify_payment(reference)
        
        if not chapa_response:
            return Response(
                {'error': 'Failed to verify payment with Chapa'}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
        # Update payment status based on Chapa response
        if chapa_response.get('status') == 'success':
            chapa_status = chapa_response['data']['status']
            
            if chapa_status == 'success':
                payment.status = 'completed'
                payment.completed_at = timezone.now()
                payment.payment_method = chapa_response['data'].get('method', '')
                payment.transaction_id = chapa_response['data'].get('tx_ref', '')
                
                # Update booking status
                payment.booking.status = 'confirmed'
                payment.booking.save()
                
                # Send confirmation email asynchronously
                send_booking_confirmation_email.delay(payment.booking.id)
                
            elif chapa_status == 'failed':
                payment.status = 'failed'
            else:
                payment.status = 'processing'
            
            payment.chapa_response = chapa_response
            payment.save()
            
            return Response({
                'success': True,
                'payment_status': payment.status,
                'booking_status': payment.booking.status,
                'transaction_id': payment.transaction_id,
                'payment_method': payment.payment_method
            })
        else:
            return Response(
                {'error': 'Payment verification failed', 'details': chapa_response}, 
                status=status.HTTP_400_BAD_REQUEST
            )
            
    except Exception as e:
        logger.error(f"Payment verification error: {str(e)}")
        return Response(
            {'error': 'Internal server error'}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['POST'])
def payment_webhook(request):
    """
    Handle Chapa webhook notifications
    """
    try:
        webhook_data = request.data
        tx_ref = webhook_data.get('tx_ref')
        
        if not tx_ref:
            return Response({'error': 'tx_ref not provided'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Get payment record
        try:
            payment = Payment.objects.get(reference=tx_ref)
        except Payment.DoesNotExist:
            logger.warning(f"Payment not found for reference: {tx_ref}")
            return Response({'error': 'Payment not found'}, status=status.HTTP_404_NOT_FOUND)
        
        # Update payment with webhook data
        payment.webhook_data = webhook_data
        
        # Update status based on webhook
        webhook_status = webhook_data.get('status')
        if webhook_status == 'success':
            payment.status = 'completed'
            payment.completed_at = timezone.now()
            payment.transaction_id = webhook_data.get('trx_ref', '')
            
            # Update booking
            payment.booking.status = 'confirmed'
            payment.booking.save()
            
            # Send confirmation email
            send_booking_confirmation_email.delay(payment.booking.id)
            
        elif webhook_status == 'failed':
            payment.status = 'failed'
        
        payment.save()
        
        return Response({'success': True})
        
    except Exception as e:
        logger.error(f"Webhook processing error: {str(e)}")
        return Response(
            {'error': 'Internal server error'}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def payment_status(request, payment_id):
    """
    Get payment status
    """
    try:
        payment = get_object_or_404(Payment, id=payment_id, user=request.user)
        serializer = PaymentSerializer(payment)
        return Response(serializer.data)
    except Exception as e:
        logger.error(f"Payment status error: {str(e)}")
        return Response(
            {'error': 'Internal server error'}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def user_payments(request):
    """
    Get user's payment history
    """
    try:
        payments = Payment.objects.filter(user=request.user)
        serializer = PaymentSerializer(payments, many=True)
        return Response(serializer.data)
    except Exception as e:
        logger.error(f"User payments error: {str(e)}")
        return Response(
            {'error': 'Internal server error'}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

# Celery task for sending confirmation emails
@shared_task
def send_booking_confirmation_email(booking_id):
    """
    Send booking confirmation email asynchronously
    """
    try:
        booking = Booking.objects.get(id=booking_id)
        user = booking.user
        
        subject = f'Booking Confirmation - {booking.listing.title}'
        
        # Render email template
        html_message = render_to_string('emails/booking_confirmation.html', {
            'user': user,
            'booking': booking,
            'listing': booking.listing,
            'payment': booking.payment
        })
        
        plain_message = f"""
        Dear {user.first_name or 'Guest'},
        
        Your booking has been confirmed!
        
        Booking Details:
        - Property: {booking.listing.title}
        - Check-in: {booking.check_in_date}
        - Check-out: {booking.check_out_date}
        - Total Amount: {booking.total_amount} ETB
        - Reference: {booking.payment.reference}
        
        Thank you for choosing ALX Travel!
        
        Best regards,
        ALX Travel Team
        """
        
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            html_message=html_message,
            fail_silently=False,
        )
        
        logger.info(f"Confirmation email sent for booking {booking_id}")
        
    except Exception as e:
        logger.error(f"Error sending confirmation email: {str(e)}")

@shared_task
def send_payment_failure_email(payment_id):
    """
    Send payment failure notification email
    """
    try:
        payment = Payment.objects.get(id=payment_id)
        user = payment.user
        booking = payment.booking
        
        subject = f'Payment Failed - {booking.listing.title}'
        
        plain_message = f"""
        Dear {user.first_name or 'Guest'},
        
        Unfortunately, your payment for the booking could not be processed.
        
        Booking Details:
        - Property: {booking.listing.title}
        - Check-in: {booking.check_in_date}
        - Check-out: {booking.check_out_date}
        - Amount: {payment.amount} ETB
        - Reference: {payment.reference}
        
        Please try again or contact our support team.
        
        Best regards,
        ALX Travel Team
        """
        
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )
        
        logger.info(f"Payment failure email sent for payment {payment_id}")
        
    except Exception as e:
        logger.error(f"Error sending payment failure email: {str(e)}")