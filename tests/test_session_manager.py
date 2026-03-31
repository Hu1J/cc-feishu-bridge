import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import tempfile
from src.claude.session_manager import SessionManager


@pytest.fixture
def manager():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    mgr = SessionManager(db_path)
    yield mgr
    Path(db_path).unlink(missing_ok=True)


def test_create_and_get_session(manager):
    session = manager.create_session("ou_123", "/Users/test/projects")
    assert session.user_id == "ou_123"
    assert session.project_path == "/Users/test/projects"
    assert session.message_count == 0

    active = manager.get_active_session("ou_123")
    assert active is not None
    assert active.session_id == session.session_id


def test_update_session(manager):
    session = manager.create_session("ou_123", "/Users/test/projects")
    manager.update_session(session.session_id, cost=0.05, message_increment=1)
    updated = manager.get_active_session("ou_123")
    assert updated.total_cost == 0.05
    assert updated.message_count == 1


def test_get_no_session(manager):
    assert manager.get_active_session("ou_unknown") is None


def test_delete_session(manager):
    session = manager.create_session("ou_123", "/Users/test/projects")
    manager.delete_session(session.session_id)
    assert manager.get_active_session("ou_123") is None