from datetime import datetime, timedelta, timezone
from typing import Union, Any
import jwt
from passlib.context import CryptContext
from cryptography.fernet import Fernet
from config import settings

# Initialize Argon2 password hashing context
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

# Fernet symmetric encryption for PHI columns; the key is validated in config.py
fernet = Fernet(settings.PHI_ENCRYPTION_KEY.encode())

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
    return fernet.encrypt(value.encode()).decode()

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
