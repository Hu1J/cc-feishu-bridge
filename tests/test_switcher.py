"""Tests for switcher.py."""
import os
import tempfile
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
             patch("cc_feishu_bridge.switcher._stop_bridge"), \
             patch("cc_feishu_bridge.switcher.os.getcwd", return_value=str(current)):
            result = switch_to(str(target))

        assert result.success, result.error_message
        assert result.target_path == str(target)

        # Read the config written to target
        written = yaml.safe_load(target_config.read_text())

        expected_db = str(target_cc / "sessions.db")
        assert written["storage"]["db_path"] == expected_db

    def test_feishu_creds_preserved(self, tmp_path):
        """app_id/app_secret are copied unchanged to target."""
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
             patch("cc_feishu_bridge.switcher._stop_bridge"), \
             patch("cc_feishu_bridge.switcher.os.getcwd", return_value=str(current)):
            result = switch_to(str(target))

        assert result.success, result.error_message

        # Read the config written to target
        written = yaml.safe_load(target_config.read_text())

        assert written["feishu"]["app_id"] == "cli_original_id"
        assert written["feishu"]["app_secret"] == "cli_original_secret"
