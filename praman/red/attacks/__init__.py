"""Attack corpus. Importing the package registers every implemented attack."""

from praman.red.attacks import semantic, structural  # noqa: F401  (imports register)
from praman.red.attacks.base import ATTACKS, Attack, AttackClass, get_attack

__all__ = ["ATTACKS", "Attack", "AttackClass", "get_attack"]
