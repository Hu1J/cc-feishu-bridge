import json
from cc_feishu_bridge.feishu.card import (
    make_auth_card,
    make_auth_success_card,
    make_auth_failed_card,
)

def test_auth_card_structure():
    card = make_auth_card(
        verification_url="https://example.com/verify",
        user_code="ABCD-1234",
        expires_minutes=5,
    )
    assert isinstance(card, dict)
    assert card["config"]["wide_screen_mode"] == False
    assert card["header"]["template"] == "blue"

def test_auth_card_contains_url_and_code():
    card = make_auth_card(
        verification_url="https://example.com/verify",
        user_code="ABCD-1234",
        expires_minutes=5,
    )
    body = card["body"]["elements"]
    # markdown element with user code
    md = next(e for e in body if e["tag"] == "markdown")
    assert "ABCD-1234" in md["content"]
    assert "example.com" in md["content"]
    # button with URL
    btn = next(e for e in body if e.get("tag") == "column_set")
    col = btn["elements"][0]
    button = col["elements"][0]
    assert button["tag"] == "button"
    assert button["type"] == "primary"
    assert "example.com" in button["multi_url"]["url"]

def test_auth_success_card():
    card = make_auth_success_card()
    assert isinstance(card, dict)
    assert card["header"]["template"] == "green"
    assert card["header"]["title"]["content"] == "✅ 授权成功"

def test_auth_failed_card():
    card = make_auth_failed_card(reason="授权已过期")
    assert isinstance(card, dict)
    assert card["header"]["template"] == "red"
    assert "授权已过期" in card["header"]["title"]["content"]