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


def test_parse_message_text_block(integration):
    """_parse_message handles TextBlock from AssistantMessage."""
    class TextBlock:
        __name__ = "TextBlock"
        def __init__(self): self.text = "Hello "

    class AssistantMessage:
        __name__ = "AssistantMessage"
        def __init__(self, blocks): self.content = blocks

    msg_obj = AssistantMessage([TextBlock()])
    msg = integration._parse_message(msg_obj)
    assert msg is not None
    assert msg.content == "Hello "
    assert msg.is_final is False


def test_parse_message_tool_use_block(integration):
    """_parse_message handles ToolUseBlock from AssistantMessage."""
    class ToolUseBlock:
        __name__ = "ToolUseBlock"
        def __init__(self): self.name = "Read"; self.input = {"file_path": "main.py"}

    class AssistantMessage:
        __name__ = "AssistantMessage"
        def __init__(self, blocks): self.content = blocks

    msg_obj = AssistantMessage([ToolUseBlock()])
    msg = integration._parse_message(msg_obj)
    assert msg is not None
    assert msg.tool_name == "Read"
    assert "main.py" in msg.tool_input


def test_parse_message_tool_result_image_block(integration):
    """_parse_message extracts image from ToolResultBlock with type=image."""
    class ToolResultBlock:
        __name__ = "ToolResultBlock"
        def __init__(self, content):
            self.content = content

    class AssistantMessage:
        __name__ = "AssistantMessage"
        def __init__(self, blocks): self.content = blocks

    msg_obj = AssistantMessage([
        ToolResultBlock([
            {"type": "image", "data": "SGVsbG8gV29ybGQ=", "mimeType": "image/png"}
        ])
    ])
    msg = integration._parse_message(msg_obj)
    assert msg is not None
    assert msg.image_data == "SGVsbG8gV29ybGQ="
    assert msg.mime_type == "image/png"


def test_parse_message_tool_result_image_data_uri(integration):
    """_parse_message extracts image from ToolResultBlock with data URI string."""
    class ToolResultBlock:
        __name__ = "ToolResultBlock"
        def __init__(self, content):
            self.content = content

    class AssistantMessage:
        __name__ = "AssistantMessage"
        def __init__(self, blocks): self.content = blocks

    msg_obj = AssistantMessage([
        ToolResultBlock("data:image/png;base64,SGVsbG9Xb3JsZA==")
    ])
    msg = integration._parse_message(msg_obj)
    assert msg is not None
    assert msg.image_data == "SGVsbG9Xb3JsZA=="
    assert msg.mime_type == "image/png"


def test_parse_message_tool_result_text_not_mistaken_for_image(integration):
    """_parse_message returns None for ToolResultBlock with plain text content."""
    class ToolResultBlock:
        __name__ = "ToolResultBlock"
        def __init__(self, content):
            self.content = content

    class AssistantMessage:
        __name__ = "AssistantMessage"
        def __init__(self, blocks): self.content = blocks

    msg_obj = AssistantMessage([
        ToolResultBlock("Image generated successfully.")
    ])
    msg = integration._parse_message(msg_obj)
    assert msg is None  # plain text result → not an image message