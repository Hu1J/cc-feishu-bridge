"""SkillSource ABC and multi-source implementations (Hermes-style)."""
from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

import httpx

from cc_feishu_bridge.skill_search.models import SkillMeta

logger = logging.getLogger(__name__)

# Trust level priority (high > trusted > community)
TRUST_PRIORITY = {"high": 0, "medium": 1, "low": 2}


class SkillSource(ABC):
    """Abstract base class for skill sources."""

    name: str  # human-readable source name

    @abstractmethod
    async def search(self, query: str, limit: int = 5) -> list[SkillMeta]:
        """Semantic search."""
        ...

    @abstractmethod
    async def get_by_name(self, name: str) -> Optional[SkillMeta]:
        """Direct lookup by exact skill name."""
        ...


# ─── Skills.sh Source ──────────────────────────────────────────────────────────


class SkillsShSource(SkillSource):
    """Search via skills.sh aggregation API.

    Ref: Hermes skills_hub.py - SkillsShSource
    API: GET https://skills.sh/api/search?q={query}&limit={limit}
    """

    name = "skills.sh"
    BASE_URL = "https://skills.sh"

    def __init__(self, timeout: float = 10.0, follow_redirects: bool = True):
        self._client = httpx.AsyncClient(timeout=timeout, follow_redirects=follow_redirects)

    async def search(self, query: str, limit: int = 5) -> list[SkillMeta]:
        try:
            resp = await self._client.get(
                f"{self.BASE_URL}/api/search",
                params={"q": query, "limit": limit},
            )
            resp.raise_for_status()
            data = resp.json()
            skills = data.get("skills", [])
            return [
                SkillMeta(
                    name=s.get("name", s.get("skillId", "")),
                    description=s.get("description", ""),
                    source=self.name,
                    identifier=s.get("id", s.get("name", "")),
                    trust_level=s.get("trust_level", "medium"),
                    tags=s.get("tags", []),
                    extra=s,
                )
                for s in skills
                if s.get("name") or s.get("skillId")
            ]
        except Exception as e:
            logger.warning(f"[SkillsShSource] search error: {e}")
            return []

    async def get_by_name(self, name: str) -> Optional[SkillMeta]:
        try:
            # Fetch skill detail page - skills.sh/{identifier}
            resp = await self._client.get(f"{self.BASE_URL}/{name}")
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            # Parse HTML for description if available
            description = ""
            # For now return minimal info - detail page parsing is complex
            return SkillMeta(
                name=name,
                description=description,
                source=self.name,
                identifier=name,
                trust_level="medium",
                tags=[],
                extra={},
            )
        except Exception as e:
            logger.warning(f"[SkillsShSource] get_by_name error: {e}")
            return None

    async def close(self):
        await self._client.aclose()


# ─── GitHub Source ─────────────────────────────────────────────────────────────


class GitHubSource(SkillSource):
    """Search GitHub repositories for skills.

    Ref: Hermes skills_hub.py - GitHubSource
    Default taps: openai/skills, anthropics/skills, VoltAgent/awesome-agent-skills, garlytan/gstack
    """

    name = "github"
    DEFAULT_TAPS = [
        {"repo": "openai/skills", "path": "skills/"},
        {"repo": "anthropics/skills", "path": "skills/"},
        {"repo": "VoltAgent/awesome-agent-skills", "path": "skills/"},
    ]

    def __init__(self, timeout: float = 10.0, follow_redirects: bool = True):
        self._client = httpx.AsyncClient(timeout=timeout, follow_redirects=follow_redirects)
        self._repo_cache: dict[str, dict] = {}  # repo -> {"tree": ..., "branch": ...}

    async def _get_default_branch(self, repo: str) -> Optional[str]:
        """Get default branch of a repo."""
        try:
            resp = await self._client.get(
                f"https://api.github.com/repos/{repo}",
                headers={"Accept": "application/vnd.github.v3+json"},
            )
            resp.raise_for_status()
            return resp.json().get("default_branch", "main")
        except Exception as e:
            logger.warning(f"[GitHubSource] failed to get default branch for {repo}: {e}")
            return None

    async def _list_directory(self, repo: str, path: str) -> list[dict]:
        """List repo directory contents."""
        try:
            resp = await self._client.get(
                f"https://api.github.com/repos/{repo}/contents/{path}",
                headers={"Accept": "application/vnd.github.v3+json"},
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.warning(f"[GitHubSource] failed to list {repo}/{path}: {e}")
            return []

    async def _fetch_file_content(self, repo: str, path: str) -> Optional[str]:
        """Fetch raw file content."""
        try:
            resp = await self._client.get(
                f"https://api.github.com/repos/{repo}/contents/{path}",
                headers={"Accept": "application/vnd.github.v3.raw"},
            )
            resp.raise_for_status()
            return resp.text
        except Exception as e:
            logger.warning(f"[GitHubSource] failed to fetch {repo}/{path}: {e}")
            return None

    async def _parse_skill_meta(self, repo: str, skill_name: str, skill_path: str) -> Optional[SkillMeta]:
        """Parse SKILL.md to extract metadata."""
        content = await self._fetch_file_content(repo, f"{skill_path}{skill_name}/SKILL.md")
        if not content:
            # Try without path prefix
            content = await self._fetch_file_content(repo, f"{skill_name}/SKILL.md")
        if not content:
            return None

        description = ""
        tags = []
        for line in content.split("\n"):
            if line.startswith("description:"):
                description = line.split(":", 1)[1].strip().strip('"').strip("'")
            elif line.startswith("tags:"):
                tags_str = line.split(":", 1)[1].strip().strip("[]")
                tags = [t.strip().strip("'").strip('"') for t in tags_str.split(",") if t.strip()]

        return SkillMeta(
            name=skill_name,
            description=description[:200] if description else "",
            source=self.name,
            identifier=f"{repo}/{skill_path}{skill_name}",
            trust_level="medium",
            tags=tags,
            extra={"repo": repo, "path": skill_path},
        )

    async def search(self, query: str, limit: int = 5) -> list[SkillMeta]:
        results = []
        query_lower = query.lower()

        for tap in self.DEFAULT_TAPS:
            repo = tap["repo"]
            path = tap["path"]

            try:
                # List skills directory
                entries = await self._list_directory(repo, path)
                for entry in entries:
                    if entry.get("type") != "dir":
                        continue
                    skill_name = entry.get("name", "")
                    if not skill_name.startswith("."):  # Skip hidden dirs
                        meta = await self._parse_skill_meta(repo, skill_name, path)
                        if meta and (query_lower in skill_name.lower() or query_lower in meta.description.lower()):
                            results.append(meta)
                            if len(results) >= limit:
                                return results
            except Exception as e:
                logger.warning(f"[GitHubSource] search error for {repo}: {e}")

        return results

    async def get_by_name(self, name: str) -> Optional[SkillMeta]:
        for tap in self.DEFAULT_TAPS:
            repo = tap["repo"]
            path = tap["path"]

            # Check if skill exists
            entries = await self._list_directory(repo, path)
            for entry in entries:
                if entry.get("type") == "dir" and entry.get("name") == name:
                    return await self._parse_skill_meta(repo, name, path)

        return None

    async def close(self):
        await self._client.aclose()


# ─── Hermes Index Source ───────────────────────────────────────────────────────


class HermesIndexSource(SkillSource):
    """Search via Hermes集中式 JSON 索引.

    Ref: Hermes skills_hub.py - HermesIndexSource
    URL: https://hermes-agent.nousresearch.com/docs/api/skills-index.json
    Cache TTL: 6 hours
    """

    name = "hermes-index"
    INDEX_URL = "https://hermes-agent.nousresearch.com/docs/api/skills-index.json"

    def __init__(self, timeout: float = 10.0, follow_redirects: bool = True):
        self._client = httpx.AsyncClient(timeout=timeout, follow_redirects=follow_redirects)
        self._cache: Optional[dict] = None

    async def _get_index(self) -> dict:
        """Get cached index."""
        if self._cache is None:
            try:
                resp = await self._client.get(self.INDEX_URL)
                resp.raise_for_status()
                self._cache = resp.json()
            except Exception as e:
                logger.warning(f"[HermesIndexSource] failed to fetch index: {e}")
                self._cache = {"skills": []}
        return self._cache

    async def search(self, query: str, limit: int = 5) -> list[SkillMeta]:
        index = await self._get_index()
        query_lower = query.lower()
        results = []

        for s in index.get("skills", []):
            name = s.get("name", "")
            desc = s.get("description", "").lower()
            if query_lower in name.lower() or query_lower in desc:
                results.append(
                    SkillMeta(
                        name=name,
                        description=s.get("description", ""),
                        source=self.name,
                        identifier=s.get("identifier", name),
                        trust_level=s.get("trust_level", "medium"),
                        tags=s.get("tags", []),
                        extra=s,
                    )
                )
                if len(results) >= limit:
                    break

        return results

    async def get_by_name(self, name: str) -> Optional[SkillMeta]:
        index = await self._get_index()

        for s in index.get("skills", []):
            if s.get("name") == name:
                return SkillMeta(
                    name=s.get("name", name),
                    description=s.get("description", ""),
                    source=self.name,
                    identifier=s.get("identifier", name),
                    trust_level=s.get("trust_level", "medium"),
                    tags=s.get("tags", []),
                    extra=s,
                )

        return None

    async def close(self):
        await self._client.aclose()


# ─── ClawHub Source ────────────────────────────────────────────────────────────


class ClawHubSource(SkillSource):
    """Search clawhub.ai.

    Ref: Hermes skills_hub.py - ClawHubSource
    API Base: https://clawhub.ai/api/v1
    Note: Always trust_level="community" per Hermes (vetting insufficient)
    """

    name = "clawhub"
    BASE_URL = "https://clawhub.ai/api/v1"

    def __init__(self, timeout: float = 10.0, follow_redirects: bool = True):
        self._client = httpx.AsyncClient(timeout=timeout, follow_redirects=follow_redirects)

    async def search(self, query: str, limit: int = 5) -> list[SkillMeta]:
        try:
            resp = await self._client.get(
                f"{self.BASE_URL}/skills",
                params={"search": query, "limit": limit},
            )
            resp.raise_for_status()
            data = resp.json()
            items = data.get("items", [])
            return [
                SkillMeta(
                    name=s.get("displayName", s.get("slug", "")),
                    description=s.get("summary", ""),
                    source=self.name,
                    identifier=f"clawhub/{s.get('slug', '')}",
                    trust_level="community",  # Per Hermes: vetting insufficient
                    tags=s.get("tags", []),
                    extra=s,
                )
                for s in items
                if s.get("slug")
            ]
        except Exception as e:
            logger.warning(f"[ClawHubSource] search error: {e}")
            return []

    async def get_by_name(self, name: str) -> Optional[SkillMeta]:
        try:
            resp = await self._client.get(f"{self.BASE_URL}/skills/{name}")
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            s = resp.json()
            return SkillMeta(
                name=s.get("displayName", name),
                description=s.get("description", s.get("summary", "")),
                source=self.name,
                identifier=f"clawhub/{name}",
                trust_level="community",
                tags=list(s.get("tags", {}).keys()) if isinstance(s.get("tags"), dict) else [],
                extra=s,
            )
        except Exception as e:
            logger.warning(f"[ClawHubSource] get_by_name error: {e}")
            return None

    async def close(self):
        await self._client.aclose()


# NOTE: SkillHub (skillhub.cn) has an API at https://api.skillhub.cn/api/v1/skills
# but it requires authentication (401). Removed until public API is available.


# ─── Claude Marketplace Source ─────────────────────────────────────────────────


class ClaudeMarketplaceSource(SkillSource):
    """Search Claude marketplace.json from GitHub repos.

    Ref: Hermes skills_hub.py - ClaudeMarketplaceSource
    Marketplace repos: anthropics/skills/.claude-plugin/marketplace.json
    """

    name = "claude-marketplace"
    MARKETPLACE_REPOS = [
        "anthropics/skills",
    ]

    def __init__(self, timeout: float = 10.0, follow_redirects: bool = True):
        self._client = httpx.AsyncClient(timeout=timeout, follow_redirects=follow_redirects)
        self._cache: dict[str, dict] = {}

    async def _fetch_marketplace(self, repo: str) -> dict:
        """Fetch marketplace.json from a repo."""
        if repo in self._cache:
            return self._cache[repo]

        try:
            resp = await self._client.get(
                f"https://api.github.com/repos/{repo}/contents/.claude-plugin/marketplace.json",
                headers={"Accept": "application/vnd.github.v3.raw"},
            )
            resp.raise_for_status()
            data = resp.json()
            self._cache[repo] = data.get("plugins", [])
            return self._cache[repo]
        except Exception as e:
            logger.warning(f"[ClaudeMarketplaceSource] failed to fetch {repo}: {e}")
            return []

    async def search(self, query: str, limit: int = 5) -> list[SkillMeta]:
        results = []
        query_lower = query.lower()

        for repo in self.MARKETPLACE_REPOS:
            plugins = await self._fetch_marketplace(repo)
            for p in plugins:
                name = p.get("name", "")
                desc = p.get("description", "").lower()
                if query_lower in name.lower() or query_lower in desc:
                    results.append(
                        SkillMeta(
                            name=name,
                            description=p.get("description", ""),
                            source=self.name,
                            identifier=f"{repo}/{name}",
                            trust_level="high",  # Official Claude repos are high trust
                            tags=p.get("tags", []),
                            extra={"repo": repo, "source_path": p.get("source", "")},
                        )
                    )
                    if len(results) >= limit:
                        return results

        return results

    async def get_by_name(self, name: str) -> Optional[SkillMeta]:
        for repo in self.MARKETPLACE_REPOS:
            plugins = await self._fetch_marketplace(repo)
            for p in plugins:
                if p.get("name") == name:
                    return SkillMeta(
                        name=name,
                        description=p.get("description", ""),
                        source=self.name,
                        identifier=f"{repo}/{name}",
                        trust_level="high",
                        tags=p.get("tags", []),
                        extra={"repo": repo, "source_path": p.get("source", "")},
                    )

        return None

    async def close(self):
        await self._client.aclose()


# ─── LobeHub Source ────────────────────────────────────────────────────────────


class LobeHubSource(SkillSource):
    """Search lobehub.com agents.

    Ref: Hermes skills_hub.py - LobeHubSource
    Index URL: https://chat-agents.lobehub.com/index.json
    """

    name = "lobehub"
    INDEX_URL = "https://chat-agents.lobehub.com/index.json"

    def __init__(self, timeout: float = 10.0, follow_redirects: bool = True):
        self._client = httpx.AsyncClient(timeout=timeout, follow_redirects=follow_redirects)
        self._cache: Optional[list] = None

    async def _get_index(self) -> list:
        """Get agents index."""
        if self._cache is None:
            try:
                resp = await self._client.get(self.INDEX_URL)
                resp.raise_for_status()
                data = resp.json()
                self._cache = data.get("agents", [])
            except Exception as e:
                logger.warning(f"[LobeHubSource] failed to fetch index: {e}")
                self._cache = []
        return self._cache

    async def search(self, query: str, limit: int = 5) -> list[SkillMeta]:
        index = await self._get_index()
        query_lower = query.lower()
        results = []

        for agent in index:
            meta = agent.get("meta", {})
            name = meta.get("title", agent.get("identifier", ""))
            desc = meta.get("description", "").lower()
            if query_lower in name.lower() or query_lower in desc:
                results.append(
                    SkillMeta(
                        name=name,
                        description=meta.get("description", ""),
                        source=self.name,
                        identifier=agent.get("identifier", name),
                        trust_level="medium",
                        tags=meta.get("tags", []),
                        extra=agent,
                    )
                )
                if len(results) >= limit:
                    break

        return results

    async def get_by_name(self, name: str) -> Optional[SkillMeta]:
        index = await self._get_index()

        for agent in index:
            meta = agent.get("meta", {})
            agent_name = meta.get("title", agent.get("identifier", ""))
            if agent_name == name:
                return SkillMeta(
                    name=agent_name,
                    description=meta.get("description", ""),
                    source=self.name,
                    identifier=agent.get("identifier", name),
                    trust_level="medium",
                    tags=meta.get("tags", []),
                    extra=agent,
                )

        return None

    async def close(self):
        await self._client.aclose()


# ─── Well-Known Skills Source ──────────────────────────────────────────────────


class WellKnownSkillSource(SkillSource):
    """Search /.well-known/skills/index.json.

    Ref: Hermes skills_hub.py - WellKnownSkillSource
    Pattern: GET https://{domain}/.well-known/skills/index.json
    """

    name = "well-known"
    WELL_KNOWN_DOMAINS = [
        "https://skills.sh",
        "https://agent.skills.sh",
    ]

    def __init__(self, timeout: float = 10.0, follow_redirects: bool = True):
        self._client = httpx.AsyncClient(timeout=timeout, follow_redirects=follow_redirects)

    async def _fetch_index(self, base_url: str) -> list:
        """Fetch well-known index from a domain."""
        url = f"{base_url.rstrip('/')}/.well-known/skills/index.json"
        try:
            resp = await self._client.get(url)
            resp.raise_for_status()
            data = resp.json()
            return data.get("skills", [])
        except Exception:
            return []

    async def search(self, query: str, limit: int = 5) -> list[SkillMeta]:
        results = []
        query_lower = query.lower()

        for base_url in self.WELL_KNOWN_DOMAINS:
            if len(results) >= limit:
                break
            skills = await self._fetch_index(base_url)
            for s in skills:
                name = s.get("name", "")
                desc = s.get("description", "").lower()
                if query_lower in name.lower() or query_lower in desc:
                    results.append(
                        SkillMeta(
                            name=name,
                            description=s.get("description", ""),
                            source=f"{self.name}-{base_url}",
                            identifier=s.get("identifier", name),
                            trust_level=s.get("trust_level", "medium"),
                            tags=s.get("tags", []),
                            extra=s,
                        )
                    )
                    if len(results) >= limit:
                        break

        return results

    async def get_by_name(self, name: str) -> Optional[SkillMeta]:
        for base_url in self.WELL_KNOWN_DOMAINS:
            skills = await self._fetch_index(base_url)
            for s in skills:
                if s.get("name") == name:
                    return SkillMeta(
                        name=name,
                        description=s.get("description", ""),
                        source=f"{self.name}-{base_url}",
                        identifier=s.get("identifier", name),
                        trust_level=s.get("trust_level", "medium"),
                        tags=s.get("tags", []),
                        extra=s,
                    )

        return None

    async def close(self):
        await self._client.aclose()
