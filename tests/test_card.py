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
    data = json.loads(card)
    assert data["msg_type"] == "interactive"
    content = json.loads(data["content"])
    assert content["config"]["wide_screen_mode"] == False
    assert content["header"]["template"] == "blue"

def test_auth_card_contains_url_and_code():
    card = make_auth_card(
        verification_url="https://example.com/verify",
        user_code="ABCD-1234",
        expires_minutes=5,
    )
    content = json.loads(json.loads(card)["content"])
    body = content["body"]["elements"]
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
    content = json.loads(json.loads(card)["content"])
    assert content["header"]["template"] == "green"
    assert content["header"]["title"]["content"] == "✅ 授权成功"

def test_auth_failed_card():
    card = make_auth_failed_card(reason="授权已过期")
    content = json.loads(json.loads(card)["content"])
    assert content["header"]["template"] == "red"
    assert "授权已过期" in content["header"]["title"]["content"]