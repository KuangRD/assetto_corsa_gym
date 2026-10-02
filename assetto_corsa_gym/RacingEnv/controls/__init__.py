"""Control backends shared across simulator adapters."""

from .keyboard import WindowsKeyboardBackend
from .vjoy import WindowsVJoyDevice

__all__ = ["WindowsKeyboardBackend", "WindowsVJoyDevice"]
