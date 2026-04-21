"""Hermes-style skill nudge — triggers skill review after N tool calls.

This module tracks tool call count per session and triggers a background
review when the threshold is reached, asking Claude Code to consider
creating or updating a skill based on recent conversation patterns.
"""
from __future__ import annotations

import asyncio
import logging
import shutil
import tempfile
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Awaitable

logger = logging.getLogger(__name__)


@dataclass
class SkillNudgeConfig:
    enabled: bool = True
    interval: int = 10  # trigger after N tool calls
    current_user: str = ""  # used as author match for auto-evolve


@dataclass
class SkillNudge:
    """Tracks tool call count and triggers review when threshold is hit."""
    config: SkillNudgeConfig
    _count: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _pending: bool = False  # True while a review is in flight

    def reset(self) -> None:
        with self._lock:
            self._count = 0
            self._pending = False

    def increment(self) -> bool:
        """Increment tool call count. Returns True if review should be triggered."""
        if not self.config.enabled:
            return False
        with self._lock:
            if self._pending:
                return False
            self._count += 1
            if self._count >= self.config.interval:
                self._pending = True
                return True
            return False

    def mark_review_done(self) -> None:
        """Call when review is complete to reset counter."""
        with self._lock:
            self._count = 0
            self._pending = False


def make_nudge(config: SkillNudgeConfig) -> SkillNudge:
    return SkillNudge(config=config)


# Review prompt shown to Claude Code when nudge fires
# Claude writes proposed skills to a staging dir; we then diff and apply
SKILL_NUDGE_PROMPT = """\
回顾上面的对话，思考以下问题：

1. 这段对话中有没有值得沉淀为可复用技能（Skill）的做法？
   适合存为 Skill 的场景：
   - 解决了非平凡问题，且解决方法可推广
   - 发现了一种新的工作流程或技巧
   - 克服了错误并找到了正确方法
   - 用户要求记住某个流程

2. 如果已有相关 Skill，有没有学到新东西可以更新它？

3. 如果要创建/更新 Skill，请先把完整内容写入临时目录（不要直接写入 ~/.claude/skills/）：
   - 临时文件路径：/tmp/skill_review_proposed/<skill-name>/SKILL.md
   - 格式：YAML frontmatter (name/description/author/version) + Markdown body
   - author 字段填你的用户名，表示这是你自己创建的

注意：
- 只创建真正有价值的 Skill，不要为了"有"而创建
- 如果有相关 Skill 已存在，优先更新它而不是创建新的
- 更新 Skill 时只改正文 instructions，不要动 frontmatter 的 name/description
"""


def _parse_skill_meta(content: str) -> tuple[str, str, str]:
    """Returns (name, description, author) from SKILL.md frontmatter."""
    name, description, author = "", "", ""
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            for line in parts[1].splitlines():
                if line.startswith("name:"):
                    name = line.split("name:", 1)[1].strip()
                elif line.startswith("description:"):
                    description = line.split("description:", 1)[1].strip()
                elif line.startswith("author:"):
                    author = line.split("author:", 1)[1].strip()
    return name, description, author


async def trigger_skill_review(
    make_claude_query: Callable[..., Awaitable[tuple]],
    project_path: str,
    nudge: SkillNudge,
    chat_id: str | None = None,
    send_to_feishu: Callable[[str, str], Awaitable[None]] | None = None,
    pending_store: dict | None = None,
) -> None:
    """Trigger a background skill review by calling Claude Code.

    Args:
        make_claude_query: a callable that runs a Claude query and returns
            (response_text, session_id, cost)
        project_path: the current project path for Claude context
        nudge: the SkillNudge instance to manage counter and pending state
        chat_id: Feishu chat_id to deliver results to (optional)
        send_to_feishu: async callable(chat_id, text) to send a Feishu message (optional)
        pending_store: dict[chat_id, list[dict]] to store pending community skill updates
    """
    if not nudge or not nudge.config.enabled:
        return

    logger.info("[skill_nudge] triggering skill review")

    skills_dir = Path.home() / ".claude" / "skills"
    proposed_dir = Path("/tmp/skill_review_proposed")

    # Snapshot existing skills: path -> (mtime, content)
    existing_snap: dict[str, tuple[float, str]] = {}
    if skills_dir.exists():
        for f in skills_dir.rglob("SKILL.md"):
            try:
                existing_snap[str(f)] = (f.stat().st_mtime, f.read_text(encoding="utf-8"))
            except OSError:
                pass

    # Clean up any previous proposed files
    if proposed_dir.exists():
        shutil.rmtree(proposed_dir)
    proposed_dir.mkdir(parents=True, exist_ok=True)

    try:
        prompt = f"项目路径：{project_path}\n\n{SKILL_NUDGE_PROMPT}"
        response, _, _ = await make_claude_query(prompt=prompt)
        logger.info(f"[skill_nudge] review done: {response[:200] if response else '(empty)'}")

        # Diff proposed dir against existing snap to find changes
        auto_changes: list[dict] = []   # user-created, apply directly
        pending_changes: list[dict] = []  # community, require confirmation

        if proposed_dir.exists():
            for f in proposed_dir.rglob("SKILL.md"):
                try:
                    new_content = f.read_text(encoding="utf-8")
                except OSError:
                    continue
                skill_name, description, author = _parse_skill_meta(new_content)
                skill_key = skills_dir / f.parent.name / "SKILL.md"
                is_new = not skill_key.exists()
                is_updated = (
                    not is_new
                    and skill_key.exists()
                    and existing_snap.get(str(skill_key), ("", ""))[1] != new_content
                )
                if not is_new and not is_updated:
                    continue

                change = {
                    "name": skill_name or f.parent.name,
                    "path": str(skill_key),
                    "description": description,
                    "author": author,
                    "proposed_path": str(f),
                    "action": "🆕 新建" if is_new else "🔄 更新",
                }
                # author matches current_user → auto-evolve; else → require confirmation
                if author and author == nudge.config.current_user:
                    auto_changes.append(change)
                else:
                    pending_changes.append(change)

        # Apply auto-change (user-created) immediately
        for c in auto_changes:
            try:
                dest = Path(c["path"])
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(c["proposed_path"], dest)
                logger.info(f"[skill_nudge] auto-evolved: {c['name']}")
            except OSError as e:
                logger.warning(f"[skill_nudge] failed to apply {c['name']}: {e}")

        # Store pending community changes; ask user to confirm
        if pending_store is not None and chat_id:
            pending_store[chat_id] = pending_changes.copy()

        # Build notification
        all_names = [c["name"] for c in auto_changes + pending_changes]
        if not all_names:
            return  # nothing happened, no notification

        parts = [c["action"] + " **" + c["name"] + "**" for c in auto_changes + pending_changes]
        msg = "🧰 Skill 自进化：" + "、".join(parts)
        if pending_changes:
            msg += "\n\n⏳ 其中社区 Skill 需回复「确认更新」后才会写入。"
        if auto_changes and pending_changes:
            msg = msg.replace("🧰 Skill 自进化：", "🧰 Skill 自进化（部分自动写入）：")

        if chat_id and send_to_feishu:
            try:
                await send_to_feishu(chat_id, msg)
            except Exception as e:
                logger.warning(f"[skill_nudge] failed to send to Feishu: {e}")

    except Exception as e:
        logger.warning(f"[skill_nudge] review failed: {e}")
    finally:
        if nudge:
            nudge.mark_review_done()


async def apply_pending_skill_updates(
    chat_id: str,
    pending_store: dict,
    send_to_feishu: Callable[[str, str], Awaitable[None]] | None = None,
) -> bool:
    """Apply all pending community skill updates for a chat_id.

    Returns True if any changes were applied.
    """
    pending = pending_store.pop(chat_id, [])
    if not pending:
        return False

    applied = []
    for c in pending:
        try:
            dest = Path(c["path"])
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(c["proposed_path"], dest)
            applied.append(c["name"])
            logger.info(f"[skill_nudge] confirmed apply: {c['name']}")
        except Exception as e:
            logger.warning(f"[skill_nudge] failed to apply {c['name']}: {e}")

    if applied and send_to_feishu:
        try:
            names = "、".join(f"**{n}**" for n in applied)
            await send_to_feishu(
                chat_id,
                f"✅ Skill 已确认写入：{names}",
            )
        except Exception as e:
            logger.warning(f"[skill_nudge] failed to send confirmation: {e}")

    return len(applied) > 0
