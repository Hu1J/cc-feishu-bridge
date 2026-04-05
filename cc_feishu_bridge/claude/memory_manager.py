"""Local memory store with SQLite FTS5 for Claude Code bridge."""
from __future__ import annotations

import logging
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

MEMORY_SYSTEM_GUIDE = """
【记忆系统使用指引】
遇到报错、构建失败、工具执行异常时，优先用 MemorySearch 搜索项目记忆。
解决问题后主动问用户："需要记住吗？" 用户确认后用 MemoryAdd 写入（标题+内容+关键词三样必填）。
用户说"记住 XXX"时，直接调用 MemoryAdd 写入。
"""


@dataclass
class UserPreference:
    """用户偏好条目（全局）"""
    id: str
    title: str
    content: str
    keywords: str  # 逗号分隔
    created_at: str
    updated_at: str


@dataclass
class ProjectMemory:
    """项目记忆条目（按项目隔离）"""
    id: str
    project_path: str
    title: str
    content: str
    keywords: str  # 逗号分隔
    created_at: str
    updated_at: str


@dataclass
class MemorySearchResult:
    """记忆搜索结果"""
    memory: ProjectMemory
    rank: float  # FTS5 bm25 rank


class MemoryManager:
    """SQLite+FTS5 双表记忆管理器"""

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            base = Path.home() / ".cc-feishu-bridge"
            base.mkdir(exist_ok=True)
            db_path = str(base / "memories.db")
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        """创建/升级数据库：删除旧表，建新表"""
        with sqlite3.connect(self.db_path) as conn:
            # 删除旧表（首次启动迁移）
            conn.execute("DROP TABLE IF EXISTS memories")
            conn.execute("DROP TABLE IF EXISTS memories_fts")
            conn.execute("DROP INDEX IF EXISTS idx_memories_project_path")
            conn.execute("DROP INDEX IF EXISTS idx_memories_type")

            # 建 user_preferences 表
            conn.execute("""
                CREATE TABLE IF NOT EXISTS user_preferences (
                    id          TEXT PRIMARY KEY,
                    title       TEXT NOT NULL,
                    content     TEXT NOT NULL,
                    keywords    TEXT NOT NULL,
                    created_at  TEXT NOT NULL,
                    updated_at  TEXT NOT NULL
                )
            """)

            # 建 user_preferences FTS5
            conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS user_preferences_fts USING fts5(
                    id UNINDEXED, title, content, keywords
                )
            """)

            # 建 project_memories 表
            conn.execute("""
                CREATE TABLE IF NOT EXISTS project_memories (
                    id           TEXT PRIMARY KEY,
                    project_path TEXT NOT NULL,
                    title        TEXT NOT NULL,
                    content      TEXT NOT NULL,
                    keywords     TEXT NOT NULL,
                    created_at   TEXT NOT NULL,
                    updated_at   TEXT NOT NULL
                )
            """)

            # 建 project_memories FTS5
            conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS project_memories_fts USING fts5(
                    id UNINDEXED, title, content, keywords
                )
            """)

    # ── 用户偏好 ───────────────────────────────────────────────────────────────

    def add_preference(
        self,
        title: str,
        content: str,
        keywords: str,
    ) -> UserPreference:
        """添加一条用户偏好（全局）"""
        now = datetime.utcnow().isoformat()
        pref = UserPreference(
            id=str(uuid.uuid4())[:8],
            title=title,
            content=content,
            keywords=keywords,
            created_at=now,
            updated_at=now,
        )
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO user_preferences (id, title, content, keywords, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (pref.id, pref.title, pref.content, pref.keywords, pref.created_at, pref.updated_at)
            )
            conn.execute(
                "INSERT INTO user_preferences_fts(id, title, content, keywords) VALUES (?, ?, ?, ?)",
                (pref.id, pref.title, pref.content, pref.keywords)
            )
        return pref

    def get_all_preferences(self) -> list[UserPreference]:
        """获取所有用户偏好（按创建时间倒序）"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM user_preferences ORDER BY created_at DESC"
            ).fetchall()
        return [UserPreference(**dict(r)) for r in rows]

    def inject_context(self, project_path: Optional[str]) -> str:
        """
        注入用户偏好到 prompt（全量返回，无搜索）。
        """
        prefs = self.get_all_preferences()
        if not prefs:
            return ""
        lines = ["\n【用户偏好】", "---"]
        for p in prefs:
            lines.append(f"**{p.title}**")
            lines.append(f"{p.content}")
            lines.append("")
        return "\n".join(lines)

    # ── 项目记忆 ───────────────────────────────────────────────────────────────

    def add_project_memory(
        self,
        project_path: str,
        title: str,
        content: str,
        keywords: str,
    ) -> ProjectMemory:
        """添加一条项目记忆（按项目隔离）"""
        now = datetime.utcnow().isoformat()
        mem = ProjectMemory(
            id=str(uuid.uuid4())[:8],
            project_path=project_path,
            title=title,
            content=content,
            keywords=keywords,
            created_at=now,
            updated_at=now,
        )
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO project_memories (id, project_path, title, content, keywords, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (mem.id, mem.project_path, mem.title, mem.content, mem.keywords, mem.created_at, mem.updated_at)
            )
            conn.execute(
                "INSERT INTO project_memories_fts(id, title, content, keywords) VALUES (?, ?, ?, ?)",
                (mem.id, mem.title, mem.content, mem.keywords)
            )
        return mem

    def search_project_memories(
        self,
        query: str,
        project_path: str,
        limit: int = 5,
    ) -> list[MemorySearchResult]:
        """按项目搜索项目记忆（只搜当前项目，全文检索）"""
        if not query.strip() or not project_path:
            return []
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT m.*, bm25(project_memories_fts) as rank
                FROM project_memories_fts
                JOIN project_memories m ON project_memories_fts.id = m.id
                WHERE project_memories_fts MATCH ?
                  AND m.project_path = ?
                ORDER BY m.created_at DESC
                LIMIT ?
            """, (query, project_path, limit)).fetchall()
        results = []
        for row in rows:
            mem = ProjectMemory(
                id=row["id"],
                project_path=row["project_path"],
                title=row["title"],
                content=row["content"],
                keywords=row["keywords"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
            results.append(MemorySearchResult(memory=mem, rank=row["rank"]))
        return results

    def delete_project_memory(self, memory_id: str) -> bool:
        """删除一条项目记忆"""
        with sqlite3.connect(self.db_path) as conn:
            affected = conn.execute(
                "DELETE FROM project_memories WHERE id = ?", (memory_id,)
            ).rowcount
        return affected > 0

    def clear_project_memories(self, project_path: str) -> int:
        """清空某项目下所有记忆"""
        if not project_path:
            return 0
        with sqlite3.connect(self.db_path) as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM project_memories WHERE project_path = ?",
                (project_path,)
            ).fetchone()[0]
            conn.execute("DELETE FROM project_memories WHERE project_path = ?", (project_path,))
        return count
