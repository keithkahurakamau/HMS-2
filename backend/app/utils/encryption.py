from cryptography.fernet import Fernet
from app.config.settings import settings
import base64

# Derives a valid 32-byte Fernet key from the JWT Secret Key
def get_fernet():
    # Pad or truncate the secret key to exactly 32 bytes
    key = settings.SECRET_KEY[:32].ljust(32, '0').encode('utf-8')
    encoded_key = base64.urlsafe_b64encode(key)
    return Fernet(encoded_key)

def encrypt_data(data: str) -> str:
    if not data:
        return None
    f = get_fernet()
    return f.encrypt(data.encode('utf-8')).decode('utf-8')

def decrypt_data(encrypted_data: str) -> str:
    if not encrypted_data:
        return None
    f = get_fernet()
    return f.decrypt(encrypted_data.encode('utf-8')).decode('utf-8')
