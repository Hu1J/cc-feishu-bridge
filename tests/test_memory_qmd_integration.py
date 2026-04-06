"""Integration test: project memory tools work with qmd."""
import pytest


def test_add_and_search_integration():
    """Add a memory via MemoryManager, then search via qmd adapter."""
    from cc_feishu_bridge.claude.qmd_adapter import get_qmd_adapter

    adapter = get_qmd_adapter()
    ok = adapter.start()
    if not ok:
        pytest.skip("qmd not available")

    proj = "/tmp/test-integration-proj"

    # Add via qmd directly
    added = adapter.add_memory(
        memory_id="int123",
        title="Integration test",
        content="Testing the integration between memory_manager and qmd",
        keywords="test,integration",
        project_path=proj,
    )
    assert added is True

    # Search
    docs = adapter.search("integration", project_path=proj, limit=5)
    assert len(docs) >= 1
    assert any("integration" in d.content.lower() for d in docs)

    # Clean up
    adapter.remove_memory("int123", proj)
    adapter.stop()


def test_memory_manager_syncs_to_qmd():
    """memory_manager.add_project_memory syncs to qmd."""
    import tempfile
    import os
    from pathlib import Path
    from cc_feishu_bridge.claude.memory_manager import MemoryManager
    from cc_feishu_bridge.claude.qmd_adapter import get_qmd_adapter

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "memories.db")
        mm = MemoryManager(db_path)
        adapter = get_qmd_adapter()
        ok = adapter.start()
        if not ok:
            pytest.skip("qmd not available")

        proj = "/tmp/test-sync-proj"
        mem = mm.add_project_memory(proj, "SyncTest", "Sync content here", "sync")

        # Verify synced to qmd (BM25 order may vary; check it appears somewhere)
        docs = adapter.search("SyncTest", project_path=proj)
        assert len(docs) >= 1
        assert any(doc.memory_id == mem.id for doc in docs)

        # Clean up
        mm.delete_project_memory(mem.id)
        adapter.stop()
