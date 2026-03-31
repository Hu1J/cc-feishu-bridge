"""Configuration loading and validation."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List

import yaml


@dataclass
class FeishuConfig:
    app_id: str
    app_secret: str
    bot_name: str = "Claude"


@dataclass
class AuthConfig:
    allowed_users: List[str] = field(default_factory=list)


@dataclass
class ClaudeConfig:
    cli_path: str = "claude"
    max_turns: int = 50
    approved_directory: str = str(Path.home())


@dataclass
class StorageConfig:
    db_path: str = "./data/sessions.db"


@dataclass
class ServerConfig:
    host: str = "0.0.0.0"
    port: int = 8080
    webhook_path: str = "/feishu/webhook"


@dataclass
class Config:
    feishu: FeishuConfig
    auth: AuthConfig
    claude: ClaudeConfig
    storage: StorageConfig
    server: ServerConfig


def load_config(path: str) -> Config:
    """Load and validate configuration from YAML file."""
    with open(path) as f:
        raw = yaml.safe_load(f)

    return Config(
        feishu=FeishuConfig(**raw.get("feishu", {})),
        auth=AuthConfig(**raw.get("auth", {})),
        claude=ClaudeConfig(**raw.get("claude", {})),
        storage=StorageConfig(**raw.get("storage", {})),
        server=ServerConfig(**raw.get("server", {})),
    )
