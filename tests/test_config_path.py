import os
import tempfile
from pathlib import Path

def test_resolve_config_path_creates_cc_dir():
    """resolve_config_path creates .cc-feishu/ in cwd if not exists."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = str(Path(tmpdir).resolve())
        os.chdir(tmpdir)
        from src.config import resolve_config_path
        cfg, data_dir = resolve_config_path()

        assert cfg == f"{tmpdir}/.cc-feishu/config.yaml"
        assert data_dir == f"{tmpdir}/.cc-feishu"
        assert Path(cfg).exists()

def test_resolve_config_path_resumes_existing():
    """If .cc-feishu/config.yaml exists, returns it (auto-resume)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = str(Path(tmpdir).resolve())
        cc_dir = Path(tmpdir) / ".cc-feishu"
        cc_dir.mkdir()
        cfg_file = cc_dir / "config.yaml"
        cfg_file.write_text("feishu:\n  app_id: test\n")

        os.chdir(tmpdir)
        from src.config import resolve_config_path
        cfg, data_dir = resolve_config_path()

        assert cfg == str(cfg_file)
        assert data_dir == str(cc_dir)