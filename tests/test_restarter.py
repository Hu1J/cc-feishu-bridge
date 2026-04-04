"""Tests for restarter.py."""
import pytest

from cc_feishu_bridge.restarter import (
    RestartError,
    StartupTimeoutError,
    RestartStep,
    RestartResult,
    _CLI_STEP_LABELS,
    _FEISHU_STEP_LABELS,
)


class TestRestartStepDataclass:
    """Tests for RestartStep dataclass fields."""

    def test_default_values(self):
        """RestartStep has correct default values."""
        step = RestartStep(step=1, total=4, label="准备重启", status="done")
        assert step.step == 1
        assert step.total == 4
        assert step.label == "准备重启"
        assert step.status == "done"
        assert step.detail == ""
        assert step.success is False
        assert step.new_pid is None

    def test_all_fields_set(self):
        """RestartStep accepts all fields including optional ones."""
        step = RestartStep(
            step=3,
            total=4,
            label="等待新进程就绪",
            status="done",
            detail="PID 12345",
            success=False,
            new_pid=12345,
        )
        assert step.step == 3
        assert step.detail == "PID 12345"
        assert step.new_pid == 12345

    def test_final_step_success(self):
        """RestartStep for final success step."""
        step = RestartStep(
            step=4,
            total=4,
            label="重启完成",
            status="final",
            detail="新 PID 99999",
            success=True,
            new_pid=99999,
        )
        assert step.success is True
        assert step.status == "final"
        assert step.new_pid == 99999


class TestRestartResultDataclass:
    """Tests for RestartResult dataclass fields."""

    def test_success_result(self):
        """RestartResult success with new_pid."""
        result = RestartResult(success=True, new_pid=12345)
        assert result.success is True
        assert result.new_pid == 12345

    def test_failure_result(self):
        """RestartResult failure with no new_pid."""
        result = RestartResult(success=False)
        assert result.success is False
        assert result.new_pid is None


class TestStepLabels:
    """Tests for step label constants."""

    def test_cli_step_labels_length(self):
        """_CLI_STEP_LABELS has 4 entries."""
        assert len(_CLI_STEP_LABELS) == 4

    def test_feishu_step_labels_length(self):
        """_FEISHU_STEP_LABELS has 4 entries."""
        assert len(_FEISHU_STEP_LABELS) == 4

    def test_cli_step_labels_match_count(self):
        """Both label lists have the same length."""
        assert len(_CLI_STEP_LABELS) == len(_FEISHU_STEP_LABELS)

    def test_cli_step_labels_content(self):
        """_CLI_STEP_LABELS contains expected Chinese labels."""
        assert "准备重启" in _CLI_STEP_LABELS
        assert "启动新 bridge" in _CLI_STEP_LABELS
        assert "等待新进程就绪" in _CLI_STEP_LABELS
        assert "重启完成" in _CLI_STEP_LABELS

    def test_feishu_step_labels_have_emoji(self):
        """_FEISHU_STEP_LABELS contains emoji."""
        for label in _FEISHU_STEP_LABELS:
            assert any(c in label for c in ["🛑", "🚀", "⏳", "✅"])


class TestExceptions:
    """Tests for exception classes."""

    def test_restart_error_is_exception(self):
        """RestartError inherits from Exception."""
        assert issubclass(RestartError, Exception)

    def test_startup_timeout_error_is_restart_error(self):
        """StartupTimeoutError inherits from RestartError."""
        assert issubclass(StartupTimeoutError, RestartError)
        assert issubclass(StartupTimeoutError, Exception)

    def test_restart_error_can_be_raised_and_caught(self):
        """RestartError can be raised and caught."""
        with pytest.raises(RestartError):
            raise RestartError("test restart error")

    def test_startup_timeout_error_can_be_raised_and_caught(self):
        """StartupTimeoutError can be raised and caught."""
        with pytest.raises(StartupTimeoutError):
            raise StartupTimeoutError("test timeout")
