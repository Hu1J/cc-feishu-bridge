"""Tests for switcher.py."""
import os
import pytest
import yaml
from unittest.mock import patch

from cc_feishu_bridge.switcher import (
    SwitchError,
    TargetStopError,
    CurrentStopError,
    StartupTimeoutError,
    switch_to,
    _copy_and_fix_config,
)


def _run_to_end(target_path, current_path=None):
    """Helper: iterate switch_to generator and return the final SwitchStep."""
    if current_path is None:
        current_path = os.getcwd()
    steps = list(switch_to(target_path))
    return steps[-1]


class TestCopyAndFixConfig:
    """Tests for _copy_and_fix_config()."""

    def test_current_not_initialized(self, tmp_path):
        """Current project has no config.yaml → SwitchError."""
        current = tmp_path / "current"
        target = tmp_path / "target"
        current.mkdir()
        target.mkdir()

        target_cc = target / ".cc-feishu-bridge"
        target_cc.mkdir()
        (target_cc / "config.yaml").write_text(yaml.dump({
            "feishu": {"app_id": "cli_target", "app_secret": "secret_target"},
        }))

        with patch("cc_feishu_bridge.switcher.os.getcwd", return_value=str(current)):
            with pytest.raises(SwitchError) as exc_info:
                _copy_and_fix_config(str(current), str(target))
        assert "当前项目未初始化" in str(exc_info.value)

    def test_db_path_rewritten_to_target(self, tmp_path):
        """storage.db_path is rewritten to target's sessions.db."""
        current = tmp_path / "current"
        target = tmp_path / "target"
        current.mkdir()
        target.mkdir()

        current_cc = current / ".cc-feishu-bridge"
        current_cc.mkdir()
        (current_cc / "config.yaml").write_text(yaml.dump({
            "feishu": {"app_id": "cli_abc", "app_secret": "secret_xyz"},
            "storage": {"db_path": "/wrong/path/sessions.db"},
        }))

        target_cc = target / ".cc-feishu-bridge"
        target_cc.mkdir()
        (target_cc / "config.yaml").write_text("")

        with patch("cc_feishu_bridge.switcher.os.getcwd", return_value=str(current)):
            _copy_and_fix_config(str(current), str(target))

        written = yaml.safe_load((target_cc / "config.yaml").read_text())
        assert written["storage"]["db_path"] == str(target_cc / "sessions.db")

    def test_current_creds_overwrite_target(self, tmp_path):
        """Current feishu credentials overwrite target's config."""
        current = tmp_path / "current"
        target = tmp_path / "target"
        current.mkdir()
        target.mkdir()

        current_cc = current / ".cc-feishu-bridge"
        current_cc.mkdir()
        (current_cc / "config.yaml").write_text(yaml.dump({
            "feishu": {"app_id": "cli_original", "app_secret": "secret_original"},
            "storage": {"db_path": "/some/path"},
        }))

        target_cc = target / ".cc-feishu-bridge"
        target_cc.mkdir()
        (target_cc / "config.yaml").write_text(yaml.dump({
            "feishu": {"app_id": "cli_target", "app_secret": "secret_target"},
        }))

        with patch("cc_feishu_bridge.switcher.os.getcwd", return_value=str(current)):
            _copy_and_fix_config(str(current), str(target))

        written = yaml.safe_load((target_cc / "config.yaml").read_text())
        assert written["feishu"]["app_id"] == "cli_original"
        assert written["feishu"]["app_secret"] == "secret_original"


class TestSwitchTo:
    """Tests for switch_to() generator."""

    def test_all_steps_yielded(self, tmp_path):
        """switch_to yields 6 steps (5 + final)."""
        current = tmp_path / "current"
        target = tmp_path / "target"
        current.mkdir()
        target.mkdir()

        current_cc = current / ".cc-feishu-bridge"
        current_cc.mkdir()
        (current_cc / "config.yaml").write_text(yaml.dump({
            "feishu": {"app_id": "cli_abc", "app_secret": "secret_xyz"},
            "storage": {},
        }))

        target_cc = target / ".cc-feishu-bridge"
        target_cc.mkdir()
        (target_cc / "config.yaml").write_text("")

        steps = list(switch_to(str(target)))
        assert len(steps) == 6  # 5 done + 1 final
        assert steps[0].step == 1
        assert steps[-1].status == "final"
        assert steps[-1].success is True

    def test_success_result(self, tmp_path):
        """On success, final step has success=True and target_pid."""
        current = tmp_path / "current"
        target = tmp_path / "target"
        current.mkdir()
        target.mkdir()

        current_cc = current / ".cc-feishu-bridge"
        current_cc.mkdir()
        (current_cc / "config.yaml").write_text(yaml.dump({
            "feishu": {"app_id": "cli_abc", "app_secret": "secret_xyz"},
            "storage": {},
        }))

        target_cc = target / ".cc-feishu-bridge"
        target_cc.mkdir()
        (target_cc / "config.yaml").write_text("")

        with patch("cc_feishu_bridge.switcher._start_bridge", return_value=99999), \
             patch("cc_feishu_bridge.switcher._stop_bridge", return_value=True), \
             patch("cc_feishu_bridge.switcher.os.getcwd", return_value=str(current)):
            final = _run_to_end(str(target))

        assert final.success is True
        assert final.target_pid == 99999

    def test_target_stop_failure_raises(self, tmp_path):
        """_stop_bridge returns False → TargetStopError raised from generator."""
        target = tmp_path / "target"
        target.mkdir()

        target_cc = target / ".cc-feishu-bridge"
        target_cc.mkdir()
        (target_cc / "config.yaml").write_text("")

        with patch("cc_feishu_bridge.switcher._stop_bridge", return_value=False):
            with pytest.raises(TargetStopError):
                list(switch_to(str(target)))

    def test_startup_timeout_raises(self, tmp_path):
        """_start_bridge raises StartupTimeoutError → exception propagates."""
        current = tmp_path / "current"
        target = tmp_path / "target"
        current.mkdir()
        target.mkdir()

        current_cc = current / ".cc-feishu-bridge"
        current_cc.mkdir()
        (current_cc / "config.yaml").write_text(yaml.dump({
            "feishu": {"app_id": "cli_abc", "app_secret": "secret_xyz"},
            "storage": {},
        }))

        target_cc = target / ".cc-feishu-bridge"
        target_cc.mkdir()
        (target_cc / "config.yaml").write_text("")

        with patch("cc_feishu_bridge.switcher._stop_bridge", return_value=True), \
             patch("cc_feishu_bridge.switcher._start_bridge",
                   side_effect=StartupTimeoutError("timeout")):
            with pytest.raises(StartupTimeoutError):
                list(switch_to(str(target)))

    def test_current_stop_failure_raises(self, tmp_path):
        """Second _stop_bridge call (current) returns False → CurrentStopError."""
        current = tmp_path / "current"
        target = tmp_path / "target"
        current.mkdir()
        target.mkdir()

        current_cc = current / ".cc-feishu-bridge"
        current_cc.mkdir()
        (current_cc / "config.yaml").write_text(yaml.dump({
            "feishu": {"app_id": "cli_abc", "app_secret": "secret_xyz"},
            "storage": {},
        }))

        target_cc = target / ".cc-feishu-bridge"
        target_cc.mkdir()
        (target_cc / "config.yaml").write_text("")

        call_count = [0]
        def stop_side_effect(path):
            call_count[0] += 1
            return call_count[0] == 1  # first (target) succeeds, second (current) fails

        with patch("cc_feishu_bridge.switcher._start_bridge", return_value=12345), \
             patch("cc_feishu_bridge.switcher._stop_bridge", side_effect=stop_side_effect), \
             patch("cc_feishu_bridge.switcher.os.getcwd", return_value=str(current)):
            with pytest.raises(CurrentStopError):
                list(switch_to(str(target)))

    def test_current_not_initialized(self, tmp_path):
        """Current project has no config → SwitchError raised."""
        current = tmp_path / "current"
        target = tmp_path / "target"
        current.mkdir()  # no .cc-feishu-bridge/
        target.mkdir()

        target_cc = target / ".cc-feishu-bridge"
        target_cc.mkdir()
        (target_cc / "config.yaml").write_text("")

        with patch("cc_feishu_bridge.switcher._stop_bridge", return_value=True), \
             patch("cc_feishu_bridge.switcher.os.getcwd", return_value=str(current)):
            with pytest.raises(SwitchError) as exc_info:
                list(switch_to(str(target)))
        assert "当前项目未初始化" in str(exc_info.value)
