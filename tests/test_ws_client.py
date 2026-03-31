import pytest
from unittest.mock import AsyncMock, MagicMock

def test_ws_client_initializes():
    from src.feishu.ws_client import FeishuWSClient
    client = FeishuWSClient(
        app_id="test_app_id",
        app_secret="test_secret",
        on_message=AsyncMock(),
    )
    assert client.app_id == "test_app_id"
    assert client.app_secret == "test_secret"
    assert client._handler is not None
    assert client._ws_client is None  # not started yet

def test_on_message_callback():
    from src.feishu.ws_client import FeishuWSClient
    cb = AsyncMock()
    client = FeishuWSClient(app_id="id", app_secret="secret", on_message=cb)

    # Mock event object simulating lark event
    mock_event = MagicMock()
    mock_event.message.message_id = "msg_123"
    mock_event.message.chat_id = "chat_abc"
    mock_event.message.msg_type = "text"
    mock_event.message.content = '{"text":"hello"}'
    mock_event.message.create_time = "1234567890"

    mock_sender = MagicMock()
    mock_sender.sender_id.open_id = "user_xyz"
    mock_event.sender = mock_sender

    client._handle_p2p_message(mock_event)
    cb.assert_called_once()
    msg = cb.call_args[0][0]
    assert msg.message_id == "msg_123"
    assert msg.chat_id == "chat_abc"
    assert msg.user_open_id == "user_xyz"
    assert msg.content == "hello"
