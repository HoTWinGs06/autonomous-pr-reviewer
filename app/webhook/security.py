"""GitHub webhook signature verification utilities."""
import hmac
import hashlib
from typing import Optional


def verify_signature(payload: bytes, signature: Optional[str], secret: str) -> bool:
    """Verify GitHub webhook HMAC-SHA256 signature."""
    if not signature or not secret:
        return False

    if not signature.startswith("sha256="):
        return False

    expected = hmac.new(
        secret.encode("utf-8"),
        payload,
        hashlib.sha256,
    ).hexdigest()

    received = signature.removeprefix("sha256=")
    return hmac.compare_digest(expected, received)
