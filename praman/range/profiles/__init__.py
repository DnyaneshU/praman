"""Rail profiles. Importing the package registers every profile."""

from praman.range.profiles.autopay import AutopayProfile
from praman.range.profiles.base import PROFILES, RailProfile, get_profile
from praman.range.profiles.uap import UapProfile

__all__ = ["RailProfile", "PROFILES", "get_profile", "AutopayProfile", "UapProfile"]
