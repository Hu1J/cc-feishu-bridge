import pytest, asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from cc_feishu_bridge.feishu.auth_flow import run_auth_flow, _poll_auth_result


class FakeDeviceAuthResult:
    def __init__(self):
        self.device_code = "dc_test123"
        self.verification_uri = "https://example.com/verify"
        self.verification_uri_complete = "https://example.com/verify?code=TESTUSER"
        self.expires_in = 300
        self.interval = 1
        self.user_code = "TESTUSER"


@pytest.mark.asyncio
async def test_sends_auth_card_then_polls():
    """run_auth_flow should send a pending card and start polling."""
    sent_cards = []

    async def mock_send_card(chat_id, card_json, reply_to=None):
        sent_cards.append(card_json)

    update_calls = []
    async def mock_update_card(msg_id, card_json):
        update_calls.append(card_json)

    token_saved = {}
    def mock_save_token(user_id, token):
        token_saved[user_id] = token

    with patch("cc_feishu_bridge.install.api.FeishuInstallAPI") as MockAPI:
        api = MockAPI.return_value
        api.device_auth_begin = AsyncMock(return_value=FakeDeviceAuthResult())
        # Return None (pending) twice, then success
        results = [None, None, {"access_token": "tok_abc", "refresh_token": "ref_xyz", "expires_in": 7200}]
        api.device_auth_poll = AsyncMock(side_effect=results)

        await run_auth_flow(
            app_id="app_123",
            app_secret="sec_456",
            user_open_id="ou_user1",
            chat_id="oc_chat1",
            message_id="om_msg1",
            send_card_fn=mock_send_card,
            update_card_fn=mock_update_card,
            save_token_fn=mock_save_token,
            scopes=["im:message", "im:file"],
        )

        # Let the background polling task complete (3 polls at interval=1s each)
        await asyncio.sleep(4)

    # Card should have been sent (make_auth_card now returns a dict, not a JSON string)
    assert len(sent_cards) == 1
    card = sent_cards[0]
    assert isinstance(card, dict)
    # Check user_code appears in markdown element
    import json
    body = card["body"]["elements"]
    md = next(e for e in body if e["tag"] == "markdown")
    assert "TESTUSER" in md["content"]
    # Token should have been saved after polling
    assert "ou_user1" in token_saved
    assert token_saved["ou_user1"]["access_token"] == "tok_abc"


@pytest.mark.asyncio
async def test_timeout_updates_card_to_failed():
    """If poll times out, card should be updated to failed state."""
    update_calls = []

    async def mock_update_card(msg_id, card_json):
        update_calls.append((msg_id, card_json))

    api = AsyncMock()
    api.device_auth_begin = AsyncMock(return_value=FakeDeviceAuthResult())
    # Always return None (never authorized) — will timeout
    api.device_auth_poll = AsyncMock(return_value=None)

    await _poll_auth_result(
        api=api,
        device_code="dc_test",
        timeout=1,  # 1 second timeout
        interval=0.3,  # poll every 0.3s
        chat_id="oc_test",
        message_id="om_test",
        update_card_fn=mock_update_card,
        save_token_fn=lambda u, t: None,
        user_open_id="ou_user",
    )

    # Should have been updated to failed
    assert len(update_calls) >= 1
    msg_id, card = update_calls[-1]
    assert msg_id == "om_test"
    # Card now a dict; check header contains error indication
    assert isinstance(card, dict)
    assert card["header"]["template"] == "red"
    assert "失败" in card["header"]["title"]["content"] or "超时" in card["header"]["title"]["content"]