"""Tests for proactive scheduler."""
from datetime import time
import pytest

from cc_feishu_bridge.proactive_scheduler import _is_in_time_window


class TestIsInTimeWindow:
    """Test _is_in_time_window helper — injects time directly, no mocking needed."""

    def test_within_daytime_window(self):
        """9am is within 08:00-22:00 window."""
        result = _is_in_time_window("08:00", "22:00", time(9, 0))
        assert result is True

    def test_outside_window_too_early(self):
        """7am is outside 08:00-22:00 window."""
        result = _is_in_time_window("08:00", "22:00", time(7, 0))
        assert result is False

    def test_outside_window_too_late(self):
        """23pm is outside 08:00-22:00 window."""
        result = _is_in_time_window("08:00", "22:00", time(23, 0))
        assert result is False

    def test_at_exact_start_boundary(self):
        """Exactly 08:00 is within the window (inclusive start)."""
        result = _is_in_time_window("08:00", "22:00", time(8, 0))
        assert result is True

    def test_at_exact_end_boundary(self):
        """Exactly 22:00 is outside the window (exclusive end)."""
        result = _is_in_time_window("08:00", "22:00", time(22, 0))
        assert result is False
