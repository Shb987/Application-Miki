import razorpay
import os
from dotenv import load_dotenv

load_dotenv()

RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID", "test_key_id")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET", "test_key_secret")

client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))

def create_razorpay_order(amount: int, currency: str = "INR", receipt: str = None):
    """
    Creates a Razorpay order. Amount should be in INR (function converts to paise internally).
    """
    data = {
        "amount": amount * 100, # Razorpay expects amount in paise
        "currency": currency,
        "receipt": receipt,
        "payment_capture": 1
    }
    order = client.order.create(data=data)
    return order

def verify_razorpay_signature(payment_id: str, order_id: str, signature: str):
    """
    Verifies the Razorpay payment signature.
    """
    try:
        client.utility.verify_payment_signature({
            'razorpay_payment_id': payment_id,
            'razorpay_order_id': order_id,
            'razorpay_signature': signature
        })
        return True
    except razorpay.errors.SignatureVerificationError:
        return False
