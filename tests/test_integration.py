import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def integration():
    from cc_feishu_bridge.claude.integration import ClaudeIntegration
    return ClaudeIntegration(cli_path="/bin/false", max_turns=10)


@pytest.mark.anyio
async def test_query_handles_missing_sdk(integration):
    with patch.dict("sys.modules", {"claude_agent_sdk": None}):
        with pytest.raises(RuntimeError, match="claude-agent-sdk is required"):
            await integration.query("hello")


def test_parse_event_stream_delta(integration):
    event = MagicMock()
    event.type = "stream_delta"
    event.content = "Hello "
    msg = integration._parse_event(event)
    assert msg is not None
    assert msg.content == "Hello "
    assert msg.is_final is False


def test_parse_event_tool_use(integration):
    event = MagicMock()
    event.type = "tool_use"
    event.name = "Read"
    event.input = {"file_path": "main.py"}
    msg = integration._parse_event(event)
    assert msg is not None
    assert msg.tool_name == "Read"
    assert "main.py" in msg.tool_input