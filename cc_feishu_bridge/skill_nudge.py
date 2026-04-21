"""Hermes-style skill nudge — triggers skill review after N tool calls.

This module tracks tool call count per session and triggers a background
review when the threshold is reached, asking Claude Code to consider
creating or updating a skill based on recent conversation patterns.
"""
from __future__ import annotations

import asyncio
import logging
import shutil
import threading
import uuid
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


class SkillSymlinkHook:
    """Monitor skills_dir and auto-create symlinks in symlink_dir.

    Uses watchdog to detect when new skill directories (containing SKILL.md) are created,
    then automatically symlinks the entire directory to symlink_dir/<skill-name>.
    """

    def __init__(
        self,
        skills_dir: Path | None = None,
        symlink_dir: Path | None = None,
    ) -> None:
        self.skills_dir = skills_dir or (Path.home() / ".cc-feishu-bridge" / "skills")
        self.symlink_dir = symlink_dir or (Path.home() / ".claude" / "skills")
        self._observer: "watchdog.Observer | None" = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start watching skills_dir in a background thread."""
        with self._lock:
            if self._observer is not None:
                return
            self._ensure_symlinks()
            from watchdog.observers import Observer
            from watchdog.events import FileSystemEventHandler, FileSystemEvent
            handler = _SymlinkHandler(self)
            self._observer = Observer()
            self._observer.schedule(handler, str(self.skills_dir), recursive=False)
            self._observer.daemon = True
            self._observer.start()
            logger.info(f"[SkillSymlinkHook] started — watching {self.skills_dir}")

    def stop(self) -> None:
        """Stop the watcher."""
        with self._lock:
            if self._observer is None:
                return
            self._observer.stop()
            self._observer.join(timeout=5)
            self._observer = None
            logger.info("[SkillSymlinkHook] stopped")

    def ensure_symlinks(self) -> None:
        """Ensure all current skills have symlinks (idempotent)."""
        self._ensure_symlinks()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _ensure_symlinks(self) -> None:
        """Create symlinks for all skills that don't have one yet."""
        if not self.skills_dir.exists():
            return
        self.symlink_dir.mkdir(parents=True, exist_ok=True)
        for skill_path in self.skills_dir.iterdir():
            if not skill_path.is_dir():
                continue
            skill_md = skill_path / "SKILL.md"
            if not skill_md.exists():
                continue
            symlink_path = self.symlink_dir / skill_path.name
            if symlink_path.exists() or symlink_path.is_symlink():
                if symlink_path.resolve() == skill_path.resolve():
                    continue
                symlink_path.unlink()
            symlink_path.symlink_to(skill_path)
            logger.info(f"[SkillSymlinkHook] linked {skill_path.name}")

    def _on_skill_created(self, skill_name: str) -> None:
        """Called by the watchdog handler when a new skill dir is detected."""
        skill_dir = self.skills_dir / skill_name
        if not (skill_dir / "SKILL.md").exists():
            return
        symlink_path = self.symlink_dir / skill_name
        if symlink_path.exists() or symlink_path.is_symlink():
            symlink_path.unlink()
        symlink_path.symlink_to(skill_dir)
        logger.info(f"[SkillSymlinkHook] linked new skill: {skill_name}")


class _SymlinkHandler:
    """FileSystemEventHandler that bridges watchdog events to SkillSymlinkHook."""

    def __init__(self, hook: SkillSymlinkHook) -> None:
        self._hook = hook

    def on_created(self, event: "FileSystemEvent") -> None:
        if event.is_directory:
            self._hook._on_skill_created(event.src_path.split("/")[-1])


# Review prompt shown to Claude Code when nudge fires
# Claude writes proposed skills to a staging dir; we then scan and apply
SKILL_NUDGE_PROMPT = """\
根据当前对话历史，判断是否有值得创建或更新的 Skill。

适合存为 Skill 的场景：
- 解决了非平凡问题，且解决方法可推广
- 发现了一种新的工作流程或技巧
- 克服了错误并找到了正确方法
- 用户要求记住某个流程

操作步骤：
1. 先查看 {SKILLS_DIR}/ 目录下已有的 Skill（如果需要更新，先拷贝到临时目录）
2. 把完整内容写入临时目录：{STAGING_PATH}/<skill-name>/SKILL.md
3. 格式：YAML frontmatter (name/description/author/version) + Markdown body

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


async def _process_skill_staging(
    staging_dir: Path,
    skills_dir: Path,
    chat_id: str | None = None,
    send_to_feishu: Callable[[str, str], Awaitable[None]] | None = None,
) -> None:
    """Scan staging dir for proposed skills, apply auto-changes, notify user."""
    auto_changes: list[dict] = []
    pending_changes: list[dict] = []

    if not staging_dir.exists():
        return

    for f in staging_dir.rglob("SKILL.md"):
        try:
            new_content = f.read_text(encoding="utf-8")
        except OSError:
            continue
        skill_name, description, author = _parse_skill_meta(new_content)
        skill_key = skills_dir / f.parent.name / "SKILL.md"
        is_new = not skill_key.exists()
        is_updated = False
        if not is_new and skill_key.exists():
            try:
                current_content = skill_key.read_text(encoding="utf-8")
                is_updated = current_content != new_content
            except OSError:
                pass
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
        # skills_dir 是实例私有的，全部都是我们自己的 skill，全部自动应用
        auto_changes.append(change)

    # Apply auto-change immediately
    for c in auto_changes:
        try:
            dest = Path(c["path"])
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(c["proposed_path"], dest)
            logger.info(f"[skill_nudge] auto-evolved: {c['name']}")
        except OSError as e:
            logger.warning(f"[skill_nudge] failed to apply {c['name']}: {e}")

    # Build notification
    if not auto_changes:
        return

    parts = [c["action"] + " **" + c["name"] + "**" for c in auto_changes]
    msg = "🧰 Skill 自进化：" + "、".join(parts)

    if chat_id and send_to_feishu:
        try:
            await send_to_feishu(chat_id, msg)
        except Exception as e:
            logger.warning(f"[skill_nudge] failed to send to Feishu: {e}")


async def trigger_skill_review(
    make_claude_query: Callable[..., Awaitable[tuple]],
    nudge: SkillNudge,
    chat_id: str | None = None,
    send_to_feishu: Callable[[str, str], Awaitable[None]] | None = None,
    pending_store: dict | None = None,
    skills_dir: Path | None = None,
    staging_dir_base: Path | None = None,
) -> None:
    """Trigger a background skill review by calling Claude Code.

    Args:
        make_claude_query: a callable that runs a Claude query and returns
            (response_text, session_id, cost)
        nudge: the SkillNudge instance to manage counter and pending state
        chat_id: Feishu chat_id to deliver results to (optional)
        send_to_feishu: async callable(chat_id, text) to send a Feishu message (optional)
        pending_store: dict[chat_id, list[dict]] to store pending community skill updates
        skills_dir: path to skills directory (defaults to ~/.cc-feishu-bridge/skills/)
        staging_dir_base: base for staging dirs (defaults to ~/.cc-feishu-bridge/skills_staging/)
    """
    if not nudge or not nudge.config.enabled:
        return

    logger.info("[skill_nudge] triggering skill review")

    skills_dir = skills_dir or (Path.home() / ".cc-feishu-bridge" / "skills")
    staging_dir_base = staging_dir_base or (Path.home() / ".cc-feishu-bridge" / "skills_staging")
    staging_id = uuid.uuid4().hex[:8]
    staging_dir = staging_dir_base / staging_id
    staging_dir.mkdir(parents=True, exist_ok=True)

    try:
        prompt = SKILL_NUDGE_PROMPT.format(
            SKILLS_DIR=str(skills_dir),
            STAGING_PATH=str(staging_dir),
        )
        response, _, _ = await make_claude_query(prompt)
        logger.info(f"[_trigger_skill_review] done: {response[:200] if response else '(empty)'}")

        # Process staging results (scan, apply, notify)
        await _process_skill_staging(
            staging_dir=staging_dir,
            skills_dir=skills_dir,
            chat_id=chat_id,
            send_to_feishu=send_to_feishu,
        )

    except Exception as e:
        logger.warning(f"[skill_nudge] review failed: {e}")
    finally:
        if staging_dir.exists():
            shutil.rmtree(staging_dir)
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
