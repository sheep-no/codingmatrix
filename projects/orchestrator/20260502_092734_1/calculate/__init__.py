"""
calculate package initialization.

This module declares the public API for the calculate package, exposing the
add function that performs numerical addition with type checking and error handling.
"""

from .calculate import add
__all__ = ['add']