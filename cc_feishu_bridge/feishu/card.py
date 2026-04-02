"""Build Feishu interactive card payloads for auth flow."""
from __future__ import annotations

import json


def _card_payload(header_title: str, header_template: str, body_elements: list) -> dict:
    return {
        "config": {"wide_screen_mode": False},
        "header": {
            "title": {"tag": "plain_text", "content": header_title},
            "template": header_template,
        },
        "body": {"elements": body_elements},
    }


def make_auth_card(verification_url: str, user_code: str, expires_minutes: int = 5) -> dict:
    """Build the pending auth card sent to the user immediately after /feishu auth."""
    return _card_payload(
        header_title="📋 授权 cc-feishu-bridge",
        header_template="blue",
        body_elements=[
            {
                "tag": "markdown",
                "content": (
                    f"**授权码：** `{user_code}`\n\n"
                    f"请在下方点击 **「前往授权」（{verification_url}）**，完成飞书授权后返回此处。\n"
                    f"链接将在 **{expires_minutes} 分钟** 后过期。\n\n"
                    "授权后机器人可执行文件上传等操作。"
                ),
            },
            {
                "tag": "column_set",
                "flex_mode": "none",
                "horizontal_align": "right",
                "elements": [
                    {
                        "tag": "column",
                        "width": "auto",
                        "elements": [
                            {
                                "tag": "button",
                                "text": {"tag": "plain_text", "content": "前往授权"},
                                "type": "primary",
                                "size": "medium",
                                "multi_url": {"url": verification_url},
                            }
                        ],
                    }
                ],
            },
        ],
    )


def make_auth_success_card() -> dict:
    """Build the success card updated after user completes auth."""
    return _card_payload(
        header_title="✅ 授权成功",
        header_template="green",
        body_elements=[
            {
                "tag": "markdown",
                "content": (
                    "🎉 授权已完成！\n\n"
                    "机器人现在可以上传文件了。\n"
                    "请继续对话或重新发送你的请求。"
                ),
            }
        ],
    )


def make_auth_failed_card(reason: str = "授权失败") -> dict:
    """Build the failed card when auth times out or is denied."""
    return _card_payload(
        header_title=f"❌ {reason}",
        header_template="red",
        body_elements=[
            {
                "tag": "markdown",
                "content": f"⚠️ {reason}\n\n请重新发送 `/feishu auth` 再次尝试。",
            }
        ],
    )