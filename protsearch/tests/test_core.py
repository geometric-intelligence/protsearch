"""
Tests for the core functionality
"""

import pytest
from protsearch import __version__


def test_version():
    """Test that version is a string."""
    assert isinstance(__version__, str)
    assert len(__version__) > 0 