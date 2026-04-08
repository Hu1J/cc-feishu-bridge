import pytest
from cc_feishu_bridge.feishu.should_respond import should_respond, _is_bot_mentioned
from cc_feishu_bridge.feishu.client import IncomingMessage
from cc_feishu_bridge.config import Config, ChatModesConfig, ChatOverrideConfig
from cc_feishu_bridge.config import FeishuConfig, AuthConfig, ClaudeConfig, StorageConfig

@pytest.fixture
def mention_mode_config():
    return Config(
        feishu=FeishuConfig(app_id="a", app_secret="s"),
        auth=AuthConfig(),
        claude=ClaudeConfig(),
        storage=StorageConfig(),
        chat_modes=ChatModesConfig(default="mention"),
    )

@pytest.fixture
def open_mode_config():
    return Config(
        feishu=FeishuConfig(app_id="a", app_secret="s"),
        auth=AuthConfig(),
        claude=ClaudeConfig(),
        storage=StorageConfig(),
        chat_modes=ChatModesConfig(default="open"),
    )

def make_group_message(chat_id, raw_content):
    return IncomingMessage(
        message_id="msg1",
        chat_id=chat_id,
        user_open_id="ou_member1",
        content="hello",
        message_type="text",
        create_time="123456",
        raw_content=raw_content,
        chat_type="group",
    )

def make_p2p_message():
    return IncomingMessage(
        message_id="msg2",
        chat_id="och_p2p",
        user_open_id="ou_user1",
        content="hello",
        message_type="text",
        create_time="123456",
        raw_content='{"text":"hi"}',
        chat_type="p2p",
    )

def test_p2p_always_responds(mention_mode_config):
    msg = make_p2p_message()
    assert should_respond(msg, mention_mode_config, "ou_bot") is True

def test_group_mention_mode_not_mentioned(mention_mode_config):
    raw = '{"text":"hello world"}'
    msg = make_group_message("och_group1", raw)
    assert should_respond(msg, mention_mode_config, "ou_bot") is False

def test_group_mention_mode_mentioned(mention_mode_config):
    raw = '{"text":"@Claude hello","mentions":[{"open_id":"ou_bot","name":"Claude"}]}'
    msg = make_group_message("och_group1", raw)
    assert should_respond(msg, mention_mode_config, "ou_bot") is True

def test_group_open_mode_always_responds(open_mode_config):
    raw = '{"text":"any message"}'
    msg = make_group_message("och_group2", raw)
    assert should_respond(msg, open_mode_config, "ou_bot") is True

def test_group_mention_mode_chat_override():
    """Group with chat_override=open should always respond."""
    cfg = Config(
        feishu=FeishuConfig(app_id="a", app_secret="s"),
        auth=AuthConfig(),
        claude=ClaudeConfig(),
        storage=StorageConfig(),
        chat_modes=ChatModesConfig(default="mention"),
        chat_overrides={"och_groupA": ChatOverrideConfig(chat_mode="open")},
    )
    msg = make_group_message("och_groupA", '{"text":"hello"}')
    assert should_respond(msg, cfg, "ou_bot") is True  # groupA uses open mode
    msg2 = make_group_message("och_groupB", '{"text":"hello"}')
    assert should_respond(msg2, cfg, "ou_bot") is False  # groupB uses default=mention, not @

def test_is_bot_mentioned():
    raw = '{"text":"@Claude hi","mentions":[{"open_id":"ou_bot123","name":"Claude"}]}'
    assert _is_bot_mentioned(raw, "ou_bot123") is True
    assert _is_bot_mentioned(raw, "ou_other") is False
    assert _is_bot_mentioned('{"text":"hello"}', "ou_bot123") is False
    assert _is_bot_mentioned("", "ou_bot123") is False
    assert _is_bot_mentioned("not json", "ou_bot123") is False