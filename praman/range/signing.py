"""ECDSA P-256 signing over a canonical JSON serialisation.

Matches AP2's documented mandate signing (P-256 / SHA-256). Keys here are
**local test keys generated at range startup** — nothing in this file touches a
real payment rail or a real HSM, and it must stay that way.

The canonical form matters more than the curve: two parties must derive
byte-identical input from the same mandate, or verification fails at random and
every result in the campaign becomes noise.
"""

from __future__ import annotations

import base64
import json
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from pydantic import BaseModel

__all__ = ["canonical_bytes", "Keyring"]

CURVE = ec.SECP256R1()
ALGORITHM = ec.ECDSA(hashes.SHA256())


def canonical_bytes(mandate: BaseModel) -> bytes:
    """Deterministic bytes for a mandate, excluding its own signature.

    `mode="json"` renders Decimal as a string and datetime as ISO-8601, so the
    representation never routes through float. Keys are sorted and separators
    are tight, so dict ordering cannot change the output.
    """
    payload: dict[str, Any] = mandate.model_dump(mode="json", exclude={"signature"})
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


class Keyring:
    """Test keypairs for the range's principals: the user, each merchant, the attacker."""

    def __init__(self) -> None:
        self._private: dict[str, ec.EllipticCurvePrivateKey] = {}

    def generate(self, holder: str) -> None:
        self._private[holder] = ec.generate_private_key(CURVE)

    def sign(self, mandate: BaseModel, holder: str) -> str:
        if holder not in self._private:
            raise KeyError(f"no key for holder {holder!r}")
        signature = self._private[holder].sign(canonical_bytes(mandate), ALGORITHM)
        return base64.b64encode(signature).decode("ascii")

    def verify(self, mandate: BaseModel, holder: str) -> bool:
        signature = getattr(mandate, "signature", None)
        if not signature or holder not in self._private:
            return False
        try:
            raw = base64.b64decode(signature, validate=True)
        except (ValueError, TypeError):
            return False
        public_key = self._private[holder].public_key()
        try:
            public_key.verify(raw, canonical_bytes(mandate), ALGORITHM)
        except (InvalidSignature, ValueError):
            return False
        return True
