"""Rail profiles. Importing the package registers every profile."""

from praman.range.profiles.autopay import AutopayProfile
from praman.range.profiles.base import PROFILES, RailProfile, get_profile

__all__ = ["RailProfile", "PROFILES", "get_profile", "AutopayProfile"]
