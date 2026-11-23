import hashlib
import hmac
import logging
import secrets
from typing import Optional

from fastapi import Header, HTTPException, Query, Security, status

from app.config import get_settings

logger = logging.getLogger("security")
settings = get_settings()


def verify_webhook_secret(
    x_webhook_secret: Optional[str] = Header(None, alias="X-Webhook-Secret"),
    apikey: Optional[str] = Header(None, alias="apikey"),
    token: Optional[str] = Query(None),
) -> bool:
    """
    Validates webhook signatures in constant time (prevents timing attacks).
    Accepts X-Webhook-Secret header, apikey header (e.g. Evolution API), or token query param.
    If WEBHOOK_SECRET is not configured or empty, allows requests in dev mode.
    """
    expected = settings.WEBHOOK_SECRET
    if not expected:
        return True  # Dev mode: open if no secret is configured

    received = x_webhook_secret or apikey or token
    if not received:
        logger.warning("Rejected webhook message: missing webhook secret/apikey.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Assinatura do webhook ausente.",
        )

    # Constant-time comparison to prevent timing attacks
    if not hmac.compare_digest(received.encode("utf-8"), expected.encode("utf-8")):
        logger.warning("Rejected webhook message: invalid signature.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Assinatura do webhook inválida.",
        )

    return True


def hash_password(password: str, iterations: int = 600_000) -> str:
    """
    Hashes passwords/keys using PBKDF2-HMAC-SHA256 with >= 600,000 iterations
    and a cryptographically random 16-byte salt.
    Format: pbkdf2_sha256${iterations}${salt_hex}${hash_hex}
    """
    salt = secrets.token_bytes(16)
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${salt.hex()}${key.hex()}"


def verify_password(password: str, hashed: str) -> bool:
    """
    Verifies a password against a PBKDF2-HMAC-SHA256 hash using constant-time comparison.
    """
    try:
        parts = hashed.split("$")
        if len(parts) != 4 or parts[0] != "pbkdf2_sha256":
            return False
        iterations = int(parts[1])
        salt = bytes.fromhex(parts[2])
        expected_key = bytes.fromhex(parts[3])

        key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
        return hmac.compare_digest(key, expected_key)
    except Exception:
        return False


def verify_admin_key(
    x_admin_key: Optional[str] = Header(None, alias="X-Admin-Key"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
) -> bool:
    """
    Protects administrative and audit endpoints via X-Admin-Key or Bearer token.
    Uses constant-time comparison against settings.ADMIN_API_KEY.
    """
    expected = settings.ADMIN_API_KEY
    if not expected:
        return True  # Dev mode: open if not configured

    received = x_admin_key
    if not received and authorization:
        if authorization.lower().startswith("bearer "):
            received = authorization[7:].strip()
        else:
            received = authorization.strip()

    if not received:
        logger.warning("Access denied: missing admin credentials.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciais administrativas ausentes.",
        )

    if not hmac.compare_digest(received.encode("utf-8"), expected.encode("utf-8")):
        logger.warning("Access denied: invalid admin credentials.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciais administrativas inválidas.",
        )

    return True
