"""Core layer - Environment management and registry"""

from .registry import EnvironmentRegistry, get_registry
from .wrapper import EnvironmentWrapper

__all__ = [
    "EnvironmentRegistry",
    "get_registry",
    "EnvironmentWrapper",
]