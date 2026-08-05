import base64
from datetime import datetime, timedelta, timezone
from typing import Union, Any
import jwt
from passlib.context import CryptContext
from cryptography.fernet import Fernet
from config import settings

# Initialize Argon2 password hashing context
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

# Initialize Fernet symmetric encryption for PHI masking
# Ensure key is correctly padded for Fernet (32 bytes urlsafe base64)
try:
    decoded_key = base64.urlsafe_b64decode(settings.PHI_ENCRYPTION_KEY)
    if len(decoded_key) < 32:
        # pad key to 32 bytes
        decoded_key = decoded_key.ljust(32, b'\0')
    elif len(decoded_key) > 32:
        decoded_key = decoded_key[:32]
    fernet_key = base64.urlsafe_b64encode(decoded_key)
except Exception:
    # fallback to a basic valid key if decode fails
    fernet_key = base64.urlsafe_b64encode(b"static_fallback_secret_32_bytes_")

fernet = Fernet(fernet_key)

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except Exception:
        return False

def encrypt_phi(value: Union[str, None]) -> Union[str, None]:
    if value is None:
        return None
    try:
        return fernet.encrypt(value.encode()).decode()
    except Exception:
        return "[ENCRYPTION_ERROR]"

def decrypt_phi(encrypted_value: Union[str, None]) -> Union[str, None]:
    if encrypted_value is None or encrypted_value.startswith("[ENCRYPTION_ERROR]"):
        return encrypted_value
    try:
        return fernet.decrypt(encrypted_value.encode()).decode()
    except Exception:
        return "[DECRYPTION_ERROR]"

def create_access_token(subject: Union[str, Any], role: str, expires_delta: timedelta = None) -> str:
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode = {"exp": expire, "sub": str(subject), "role": role, "type": "access"}
    return jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)

def create_refresh_token(subject: Union[str, Any], expires_delta: timedelta = None) -> str:
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
        
    to_encode = {"exp": expire, "sub": str(subject), "type": "refresh"}
    return jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)

def decode_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        return payload
    except jwt.PyJWTError:
        return {}
