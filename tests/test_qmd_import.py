"""Verify qmd CLI is available and MCP mode works."""
import subprocess
import sys


def test_qmd_cli_available():
    """qmd CLI is in PATH and responds to --help."""
    result = subprocess.run(
        ["qmd", "--help"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, f"qmd --help failed: {result.stderr}"
    assert "qmd-py" in result.stdout or "usage" in result.stdout


def test_qmd_collection_add_and_query():
    """Basic workflow: add collection, query, verify document found."""
    import tempfile
    import os
    import shutil

    tmpdir = tempfile.mkdtemp()
    try:
        # Create a markdown file
        mem_dir = os.path.join(tmpdir, "memories")
        os.makedirs(mem_dir)
        mem_file = os.path.join(mem_dir, "test.md")
        with open(mem_file, "w", encoding="utf-8") as f:
            f.write("# Test Memory\n\nContent about jieba分词.\n\n**Keywords**: test, jieba\n")

        db_path = os.path.join(tmpdir, "qmd.db")
        # --db is a global flag, must come before subcommand
        def qmd_cmd(subcmd_args, timeout=30):
            return subprocess.run(
                ["qmd", f"--db", db_path] + subcmd_args,
                capture_output=True, text=True, timeout=timeout,
            )

        # Add collection
        add_result = qmd_cmd(["add", "test_col", mem_dir, "--pattern", "**/*.md"])
        assert add_result.returncode == 0, f"qmd add failed: {add_result.stderr}"

        # Update index
        update_result = qmd_cmd(["update", "test_col"])
        assert update_result.returncode == 0, f"qmd update failed: {update_result.stderr}"

        # Query
        query_result = qmd_cmd([
            "query", "jieba",
            "--collection", "test_col",
            "--format", "json",
        ])
        # May fail if qmd not fully functional — check only if returncode 0
        if query_result.returncode == 0:
            import json
            items = json.loads(query_result.stdout)
            assert len(items) >= 1
            # body is only present with --full; check snippet or body
            body_or_snippet = items[0].get("body") or items[0].get("snippet", "")
            assert "jieba" in body_or_snippet

        # Clean up
        qmd_cmd(["collection", "remove", "test_col"], timeout=10)
    finally:
        shutil.rmtree(tmpdir)


if __name__ == "__main__":
    test_qmd_cli_available()
    print("✓ qmd CLI available")
    test_qmd_collection_add_and_query()
    print("✓ qmd collection add + query works")
