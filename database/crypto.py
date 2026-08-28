from cryptography.fernet import Fernet

from config import Config

_fernet = None


def get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        key = Config.SECRET_KEY
        if not key:
            raise ValueError(
                "SECRET_KEY is missing. Generate one with:\n"
                "  python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\"\n"
                "and set it as SECRET_KEY in your .env — this key encrypts every stored site secret."
            )
        _fernet = Fernet(key.encode() if isinstance(key, str) else key)
    return _fernet


def encrypt(value: str) -> str:
    return get_fernet().encrypt(value.encode()).decode()


def decrypt(token: str) -> str:
    return get_fernet().decrypt(token.encode()).decode()
