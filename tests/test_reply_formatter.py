import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from src.format.reply_formatter import ReplyFormatter, FEISHU_MAX_MESSAGE_LENGTH


@pytest.fixture
def formatter():
    return ReplyFormatter()


def test_format_basic_text(formatter):
    result = formatter.format_text("Hello world")
    assert result == "Hello world"


def test_format_with_code(formatter):
    result = formatter.format_text("Use `print()` to debug")
    assert "`print()`" in result


def test_format_tool_call(formatter):
    result = formatter.format_tool_call("Read", "src/main.py")
    assert "📖" in result
    assert "Read" in result
    assert "src/main.py" in result


def test_split_messages_short(formatter):
    chunks = formatter.split_messages("Short message")
    assert len(chunks) == 1
    assert chunks[0] == "Short message"


def test_split_messages_long(formatter):
    long_text = "x" * 5000
    chunks = formatter.split_messages(long_text)
    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk) <= FEISHU_MAX_MESSAGE_LENGTH