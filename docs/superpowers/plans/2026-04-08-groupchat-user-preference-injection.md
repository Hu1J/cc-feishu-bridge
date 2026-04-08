# 群聊用户偏好注入条件 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在群聊 `open` 模式（不艾特也回答）下，当 CC 响应但用户未被艾特时，跳过用户偏好注入；被艾特时仍正常注入。

**Architecture:** 修改 `message_handler.py` 中 `inject_context` 的调用逻辑，增加 `chat_type` 和 `@mention` 判断；复用 `should_respond.py` 中已有的 `_is_bot_mentioned()` 函数。

**Tech Stack:** Python, pytest

---

## 文件变更概览

| 文件 | 变更 |
|------|------|
| `cc_feishu_bridge/feishu/message_handler.py` | 修改 import 和 `_process_message_with_session()` 中的偏好注入逻辑 |
| `tests/test_should_respond.py` | 新增偏好注入条件测试用例 |

---

## 任务 1: 修改 message_handler.py

**Files:**
- Modify: `cc_feishu_bridge/feishu/message_handler.py:20` (import)
- Modify: `cc_feishu_bridge/feishu/message_handler.py:278-282` (注入逻辑)

- [ ] **Step 1: 修改 import，添加 `_is_bot_mentioned`**

文件第 20 行：
```python
from cc_feishu_bridge.feishu.should_respond import should_respond
```
改为：
```python
from cc_feishu_bridge.feishu.should_respond import should_respond, _is_bot_mentioned
```

- [ ] **Step 2: 修改 `_process_message_with_session()` 中的偏好注入逻辑**

约第 278-282 行，当前代码：
```python
system_prompt_append = (
    MEMORY_SYSTEM_GUIDE
    + FEISHU_FILE_GUIDE
    + self.memory_manager.inject_context(user_open_id=message.user_open_id)
)
```

改为：
```python
# 只有在用户明确与 CC 互动时才注入偏好：
# - P2P 私聊：始终注入
# - 群聊被 @mention：注入
# - 群聊 open 模式但未被 mention：跳过（回复对象不明确）
should_inject = (
    message.chat_type == "p2p"
    or _is_bot_mentioned(message.raw_content, self._bot_open_id)
)
user_pref_context = (
    self.memory_manager.inject_context(user_open_id=message.user_open_id)
    if should_inject else ""
)
system_prompt_append = (
    MEMORY_SYSTEM_GUIDE
    + FEISHU_FILE_GUIDE
    + user_pref_context
)
```

- [ ] **Step 3: 运行现有测试确保没有回归**

```bash
cd /Users/x/.openclaw/workspace/cc-feishu-bridge && python -m pytest tests/test_should_respond.py -v
```

Expected: PASS（所有现有测试不变）

- [ ] **Step 4: Commit**

```bash
git add cc_feishu_bridge/feishu/message_handler.py
git commit -m "$(cat <<'EOF'
feat(message_handler): skip user preference injection in group open mode without @mention

Only inject user preferences when the user is clearly interacting with CC:
- P2P: always inject
- Group chat with @mention: inject
- Group chat open mode without @mention: skip (response target is ambiguous)

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## 任务 2: 新增测试用例

**Files:**
- Modify: `tests/test_should_respond.py`

- [ ] **Step 1: 添加新测试函数 `test_should_inject_preferences`**

在 `test_should_respond.py` 末尾添加：

```python
def test_should_inject_preferences_p2p(memory_mgr):
    """P2P 私聊应注入偏好"""
    memory_mgr.add_preference("ou_user1", "主人信息", "我叫狗蛋", "狗蛋")
    ctx = memory_mgr.inject_context("ou_user1")
    assert "我叫狗蛋" in ctx


def test_should_inject_preferences_group_mentioned(memory_mgr):
    """群聊被 @mention 应注入偏好"""
    memory_mgr.add_preference("ou_user1", "主人信息", "我叫狗蛋", "狗蛋")
    # 模拟群聊被 mention 的 raw_content
    raw = '{"text":"@Claude hello","mentions":[{"open_id":"ou_bot","name":"Claude"}]}'
    assert _is_bot_mentioned(raw, "ou_bot") is True
    ctx = memory_mgr.inject_context("ou_user1")
    assert "我叫狗蛋" in ctx


def test_should_not_inject_preferences_group_open_no_mention(memory_mgr):
    """群聊 open 模式未被 @mention 不应注入偏好（通过 inject_context 返回空判断）"""
    # 注意：inject_context 本身不判断场景，只按 user_open_id 查询
    # 这里测试 inject_context 在无偏好时返回空字符串
    memory_mgr.add_preference("ou_user1", "主人信息", "我叫狗蛋", "狗蛋")
    # 另一个用户 ou_user2 没有设置偏好
    ctx = memory_mgr.inject_context("ou_user2")
    assert ctx == ""
```

**注意：** `inject_context` 本身不判断场景，测试重点是 `_is_bot_mentioned` 在不同场景下的返回值。新增一个测试文件来测试 message_handler 的偏好注入条件逻辑。

- [ ] **Step 2: 创建新测试文件 `tests/test_message_handler_preference_injection.py`**

创建文件：
```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from cc_feishu_bridge.feishu.should_respond import _is_bot_mentioned
from cc_feishu_bridge.feishu.client import IncomingMessage

BOT_OPEN_ID = "ou_bot"

def make_group_message(chat_id, raw_content, user_open_id="ou_member1"):
    return IncomingMessage(
        message_id="msg1",
        chat_id=chat_id,
        user_open_id=user_open_id,
        content="hello",
        message_type="text",
        create_time="123456",
        raw_content=raw_content,
        chat_type="group",
    )

def make_p2p_message(user_open_id="ou_user1"):
    return IncomingMessage(
        message_id="msg2",
        chat_id="och_p2p",
        user_open_id=user_open_id,
        content="hello",
        message_type="text",
        create_time="123456",
        raw_content='{"text":"hi"}',
        chat_type="p2p",
    )


class TestPreferenceInjectionCondition:
    """测试偏好注入条件判断逻辑"""

    def test_p2p_should_inject(self):
        """P2P 私聊 → 应注入偏好"""
        msg = make_p2p_message()
        should_inject = (
            msg.chat_type == "p2p"
            or _is_bot_mentioned(msg.raw_content, BOT_OPEN_ID)
        )
        assert should_inject is True

    def test_group_mention_mode_mentioned_should_inject(self):
        """群聊 mention 模式，被 @ → 应注入偏好"""
        raw = '{"text":"@Claude hello","mentions":[{"open_id":"ou_bot","name":"Claude"}]}'
        msg = make_group_message("och_group1", raw)
        should_inject = (
            msg.chat_type == "p2p"
            or _is_bot_mentioned(msg.raw_content, BOT_OPEN_ID)
        )
        assert should_inject is True

    def test_group_open_mode_mentioned_should_inject(self):
        """群聊 open 模式，被 @ → 应注入偏好"""
        raw = '{"text":"@Claude hi","mentions":[{"open_id":"ou_bot","name":"Claude"}]}'
        msg = make_group_message("och_group2", raw)
        should_inject = (
            msg.chat_type == "p2p"
            or _is_bot_mentioned(msg.raw_content, BOT_OPEN_ID)
        )
        assert should_inject is True

    def test_group_open_mode_no_mention_should_not_inject(self):
        """群聊 open 模式，未被 @ → 不应注入偏好"""
        raw = '{"text":"hello world"}'
        msg = make_group_message("och_group3", raw)
        should_inject = (
            msg.chat_type == "p2p"
            or _is_bot_mentioned(msg.raw_content, BOT_OPEN_ID)
        )
        assert should_inject is False

    def test_group_mention_mode_not_mentioned_should_not_inject(self):
        """群聊 mention 模式，未被 @ → 不应注入偏好（should_respond 已返回 False）"""
        raw = '{"text":"just chat"}'
        msg = make_group_message("och_group4", raw)
        should_inject = (
            msg.chat_type == "p2p"
            or _is_bot_mentioned(msg.raw_content, BOT_OPEN_ID)
        )
        assert should_inject is False
```

- [ ] **Step 3: 运行新测试**

```bash
python -m pytest tests/test_message_handler_preference_injection.py -v
```

Expected: PASS（5 个测试全部通过）

- [ ] **Step 4: Commit**

```bash
git add tests/test_message_handler_preference_injection.py tests/test_should_respond.py
git commit -m "$(cat <<'EOF'
test: add preference injection condition tests for group chat scenarios

Verify that user preferences are only injected when:
- P2P chat (always)
- Group chat with @mention (always)
- Group open mode without @mention (skip)

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## 自检清单

- [ ] Spec 中每条需求都有对应任务实现
- [ ] 无 placeholder (TBD/TODO)
- [ ] 类型、方法名在多个任务间一致
- [ ] 现有 `test_should_respond.py` 测试全部 PASS
- [ ] 新测试文件 `test_message_handler_preference_injection.py` 5 个测试 PASS
- [ ] 两次 commit，分类清晰
