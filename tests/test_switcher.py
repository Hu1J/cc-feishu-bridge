"""Tests for switcher.py."""
import os
from pathlib import Path

import pytest
import yaml
from unittest.mock import patch

from cc_feishu_bridge.switcher import (
    SwitchError,
    NotInitializedError,
    TargetStopError,
    CurrentStopError,
    StartupTimeoutError,
    SwitchResult,
    switch_to,
    _check_target_initialized,
    _copy_and_fix_config,
)


class TestCheckTargetInitialized:
    """Tests for _check_target_initialized()."""

    def test_target_not_initialized_no_config(self, tmp_path):
        """Target dir has no .cc-feishu-bridge/config.yaml → NotInitializedError."""
        target = tmp_path / "target_project"
        target.mkdir()

        with pytest.raises(NotInitializedError) as exc_info:
            _check_target_initialized(str(target))

        assert "config.yaml not found" in str(exc_info.value)

    def test_target_not_initialized_empty_config(self, tmp_path):
        """Target has empty config.yaml → NotInitializedError."""
        target = tmp_path / "target_project"
        target.mkdir()
        cc_dir = target / ".cc-feishu-bridge"
        cc_dir.mkdir()
        config_path = cc_dir / "config.yaml"
        config_path.write_text("")  # empty file

        with pytest.raises(NotInitializedError) as exc_info:
            _check_target_initialized(str(target))

        assert "empty" in str(exc_info.value)

    def test_target_not_initialized_missing_creds(self, tmp_path):
        """Target has config but no feishu credentials → NotInitializedError."""
        target = tmp_path / "target_project"
        target.mkdir()
        cc_dir = target / ".cc-feishu-bridge"
        cc_dir.mkdir()
        config_path = cc_dir / "config.yaml"
        config_path.write_text(yaml.dump({"auth": {}}))  # no feishu section

        with pytest.raises(NotInitializedError) as exc_info:
            _check_target_initialized(str(target))

        assert "missing feishu.app_id or feishu.app_secret" in str(exc_info.value)

    def test_target_initialized_with_creds(self, tmp_path):
        """Target has valid config with feishu credentials → no error."""
        target = tmp_path / "target_project"
        target.mkdir()
        cc_dir = target / ".cc-feishu-bridge"
        cc_dir.mkdir()
        config_path = cc_dir / "config.yaml"
        config_path.write_text(yaml.dump({
            "feishu": {"app_id": "cli_abc", "app_secret": "secret_xyz"},
        }))

        # Should not raise
        _check_target_initialized(str(target))


class TestSwitchTo:
    """Tests for switch_to()."""

    def test_db_path_rewritten_to_target(self, tmp_path):
        """storage.db_path is rewritten to target's .cc-feishu-bridge/sessions.db."""
        current = tmp_path / "current"
        target = tmp_path / "target"
        current.mkdir()
        target.mkdir()

        # Current config (used as source)
        current_cc = current / ".cc-feishu-bridge"
        current_cc.mkdir()
        current_config = current_cc / "config.yaml"
        current_config.write_text(yaml.dump({
            "feishu": {"app_id": "cli_abc", "app_secret": "secret_xyz"},
            "storage": {"db_path": "/completely/different/path/sessions.db"},
        }))

        # Target must already have a valid config (to pass initialization check)
        target_cc = target / ".cc-feishu-bridge"
        target_cc.mkdir()
        target_config = target_cc / "config.yaml"
        target_config.write_text(yaml.dump({
            "feishu": {"app_id": "cli_target", "app_secret": "secret_target"},
        }))

        with patch("cc_feishu_bridge.switcher._start_bridge") as mock_start, \
             patch("cc_feishu_bridge.switcher._stop_bridge", return_value=True), \
             patch("cc_feishu_bridge.switcher.os.getcwd", return_value=str(current)):
            result = switch_to(str(target))

        assert result.success, result.error_message
        assert result.target_path == str(target)

        # Read the config written to target
        written = yaml.safe_load(target_config.read_text())

        expected_db = str(target_cc / "sessions.db")
        assert written["storage"]["db_path"] == expected_db

    def test_current_creds_written_to_target(self, tmp_path):
        """Current app_id/app_secret are written to target (overwriting target's creds)."""
        current = tmp_path / "current"
        target = tmp_path / "target"
        current.mkdir()
        target.mkdir()

        # Current config
        current_cc = current / ".cc-feishu-bridge"
        current_cc.mkdir()
        current_config = current_cc / "config.yaml"
        current_config.write_text(yaml.dump({
            "feishu": {"app_id": "cli_original_id", "app_secret": "cli_original_secret"},
            "storage": {"db_path": "/some/path/sessions.db"},
        }))

        # Target must already have a valid config (to pass initialization check)
        target_cc = target / ".cc-feishu-bridge"
        target_cc.mkdir()
        target_config = target_cc / "config.yaml"
        target_config.write_text(yaml.dump({
            "feishu": {"app_id": "cli_target", "app_secret": "secret_target"},
        }))

        with patch("cc_feishu_bridge.switcher._start_bridge") as mock_start, \
             patch("cc_feishu_bridge.switcher._stop_bridge", return_value=True), \
             patch("cc_feishu_bridge.switcher.os.getcwd", return_value=str(current)):
            result = switch_to(str(target))

        assert result.success, result.error_message

        # Read the config written to target
        written = yaml.safe_load(target_config.read_text())

        assert written["feishu"]["app_id"] == "cli_original_id"
        assert written["feishu"]["app_secret"] == "cli_original_secret"

    def test_target_stop_failure(self, tmp_path):
        """_stop_bridge returns False for target → TargetStopError raised."""
        target = tmp_path / "target"
        target.mkdir()

        target_cc = target / ".cc-feishu-bridge"
        target_cc.mkdir()
        target_config = target_cc / "config.yaml"
        target_config.write_text(yaml.dump({
            "feishu": {"app_id": "cli_abc", "app_secret": "secret_xyz"},
        }))

        with patch("cc_feishu_bridge.switcher._stop_bridge", return_value=False):
            with pytest.raises(TargetStopError) as exc_info:
                switch_to(str(target))

        assert "Failed to stop target bridge" in str(exc_info.value)

    def test_startup_timeout(self, tmp_path):
        """_start_bridge raises StartupTimeoutError → error result returned."""
        current = tmp_path / "current"
        target = tmp_path / "target"
        current.mkdir()
        target.mkdir()

        current_cc = current / ".cc-feishu-bridge"
        current_cc.mkdir()
        (current_cc / "config.yaml").write_text(yaml.dump({
            "feishu": {"app_id": "cli_abc", "app_secret": "secret_xyz"},
            "storage": {"db_path": "/some/path/sessions.db"},
        }))

        target_cc = target / ".cc-feishu-bridge"
        target_cc.mkdir()
        (target_cc / "config.yaml").write_text(yaml.dump({
            "feishu": {"app_id": "cli_target", "app_secret": "secret_target"},
        }))

        with patch("cc_feishu_bridge.switcher._stop_bridge", return_value=True), \
             patch("cc_feishu_bridge.switcher._start_bridge",
                   side_effect=StartupTimeoutError("timeout")):
            result = switch_to(str(target))

        assert result.success is False
        assert result.error_step == "start_target"
        assert "timeout" in result.error_message

    def test_current_stop_failure(self, tmp_path):
        """_stop_bridge returns False for current after target starts → CurrentStopError raised."""
        current = tmp_path / "current"
        target = tmp_path / "target"
        current.mkdir()
        target.mkdir()

        current_cc = current / ".cc-feishu-bridge"
        current_cc.mkdir()
        (current_cc / "config.yaml").write_text(yaml.dump({
            "feishu": {"app_id": "cli_abc", "app_secret": "secret_xyz"},
            "storage": {"db_path": "/some/path/sessions.db"},
        }))

        target_cc = target / ".cc-feishu-bridge"
        target_cc.mkdir()
        (target_cc / "config.yaml").write_text(yaml.dump({
            "feishu": {"app_id": "cli_target", "app_secret": "secret_target"},
        }))

        call_count = [0]
        def stop_bridge_side_effect(path):
            call_count[0] += 1
            # First call is for target (step 2) — succeed
            # Second call is for current (step 5) — fail
            return call_count[0] == 1

        with patch("cc_feishu_bridge.switcher._start_bridge", return_value=12345), \
             patch("cc_feishu_bridge.switcher._stop_bridge", side_effect=stop_bridge_side_effect), \
             patch("cc_feishu_bridge.switcher.os.getcwd", return_value=str(current)):
            with pytest.raises(CurrentStopError) as exc_info:
                switch_to(str(target))

        assert "Could not stop current bridge" in str(exc_info.value)

    def test_current_not_initialized(self, tmp_path):
        """Current project has no config.yaml → SwitchError in copy_config step."""
        current = tmp_path / "current"
        target = tmp_path / "target"
        current.mkdir()  # no .cc-feishu-bridge/config.yaml
        target.mkdir()

        target_cc = target / ".cc-feishu-bridge"
        target_cc.mkdir()
        (target_cc / "config.yaml").write_text(yaml.dump({
            "feishu": {"app_id": "cli_target", "app_secret": "secret_target"},
        }))

        with patch("cc_feishu_bridge.switcher._stop_bridge", return_value=True), \
             patch("cc_feishu_bridge.switcher.os.getcwd", return_value=str(current)):
            result = switch_to(str(target))

        assert result.success is False
        assert result.error_step == "copy_config"
        assert "当前项目未初始化" in result.error_message


