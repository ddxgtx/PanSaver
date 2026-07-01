import os
import base64
import hashlib
from cryptography.fernet import Fernet
from app.utils.paths import get_data_dir
from loguru import logger

_key = None

def get_secret_key_path() -> str:
    return str(get_data_dir() / 'secret.key')

def init_crypto():
    """Initializes or loads the secret key for Fernet symmetric encryption."""
    global _key
    key_path = get_secret_key_path()
    try:
        if os.path.exists(key_path):
            with open(key_path, 'rb') as f:
                _key = f.read()
            logger.info("Loaded encryption key from secret.key.")
        else:
            _key = Fernet.generate_key()
            with open(key_path, 'wb') as f:
                f.write(_key)
            # Set read/write permissions for owner only on Unix-like systems
            if os.name != 'nt':
                try:
                    os.chmod(key_path, 0o600)
                except Exception as ex:
                    logger.warning(f"Could not set file permissions on secret.key: {ex}")
            logger.info("Generated new encryption key and saved to secret.key.")
    except Exception as e:
        logger.error(f"Failed to initialize encryption key: {e}")
        raise e

def encrypt(data: str) -> str:
    """Encrypts a plaintext string to an encrypted string."""
    if not data:
        return ""
    global _key
    if _key is None:
        init_crypto()
    f = Fernet(_key)
    return f.encrypt(data.encode('utf-8')).decode('utf-8')

def decrypt(encrypted_data: str) -> str:
    """Decrypts an encrypted string to a plaintext string."""
    if not encrypted_data:
        return ""
    global _key
    if _key is None:
        init_crypto()
    f = Fernet(_key)
    try:
        return f.decrypt(encrypted_data.encode('utf-8')).decode('utf-8')
    except Exception as e:
        logger.error(f"Decryption failed. Check key integrity: {e}")
        raise ValueError("Decryption failed") from e

def hash_password(password: str, salt: bytes = None) -> str:
    """Hashes a password using PBKDF2 with 100,000 iterations of SHA-256."""
    if salt is None:
        salt = os.urandom(16)
    key = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
    salt_b64 = base64.b64encode(salt).decode('utf-8')
    key_b64 = base64.b64encode(key).decode('utf-8')
    return f"pbkdf2_sha256$100000${salt_b64}${key_b64}"

def verify_password(password: str, hashed: str) -> bool:
    """Verifies a password against its PBKDF2 hash."""
    try:
        parts = hashed.split('$')
        if len(parts) != 4 or parts[0] != 'pbkdf2_sha256':
            return False
        iterations = int(parts[1])
        salt = base64.b64decode(parts[2].encode('utf-8'))
        key = base64.b64decode(parts[3].encode('utf-8'))
        
        test_key = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, iterations)
        return test_key == key
    except Exception as e:
        logger.error(f"Password verification error: {e}")
        return False
