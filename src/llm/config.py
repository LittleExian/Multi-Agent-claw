from __future__ import annotations

import os
from pathlib import Path

from pydantic import Field

from src.shared.schemas import JSONDict, SwarmSchema


def _read_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _read_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _read_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


class ModelProfile(SwarmSchema):
    name: str = "default"
    provider: str = "openai_compatible"
    model: str
    api_key: str
    base_url: str | None = None
    temperature: float = 0.2
    max_tokens: int = 1400
    timeout_seconds: float = 60.0
    supports_tools: bool = True
    extra_headers: JSONDict = Field(default_factory=dict)


class LLMRuntimeConfig(SwarmSchema):
    workspace_root: str
    default_profile: str = "default"
    max_tool_rounds: int = 6
    max_read_chars: int = 12000
    browser_timeout_seconds: int = 15
    shell_timeout_seconds: int = 60
    shell_network_enabled: bool = False
    profiles: dict[str, ModelProfile] = Field(default_factory=dict)

    @classmethod
    def from_env(cls) -> "LLMRuntimeConfig":
        base_url = os.getenv("SWARM_LLM_BASE_URL") or os.getenv("OPENAI_BASE_URL")
        api_key = os.getenv("SWARM_LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
        model = os.getenv("SWARM_LLM_MODEL")
        workspace_root = os.getenv("SWARM_WORKSPACE_ROOT") or str(
            Path(__file__).resolve().parents[2]
        )

        profiles: dict[str, ModelProfile] = {}
        if model:
            profiles["default"] = ModelProfile(
                model=model,
                api_key=api_key or ("local" if base_url else ""),
                base_url=base_url,
                temperature=_read_float("SWARM_LLM_TEMPERATURE", 0.2),
                max_tokens=_read_int("SWARM_LLM_MAX_TOKENS", 1400),
                timeout_seconds=_read_float("SWARM_LLM_TIMEOUT_SECONDS", 60.0),
                supports_tools=_read_bool("SWARM_LLM_SUPPORTS_TOOLS", True),
            )

        return cls(
            workspace_root=workspace_root,
            max_tool_rounds=_read_int("SWARM_LLM_MAX_TOOL_ROUNDS", 6),
            max_read_chars=_read_int("SWARM_MAX_READ_CHARS", 12000),
            browser_timeout_seconds=_read_int("SWARM_BROWSER_TIMEOUT_SECONDS", 15),
            shell_timeout_seconds=_read_int("SWARM_SHELL_TIMEOUT_SECONDS", 60),
            shell_network_enabled=_read_bool("SWARM_SHELL_NETWORK_ENABLED", False),
            profiles=profiles,
        )

    def is_configured(self) -> bool:
        profile = self.profiles.get(self.default_profile)
        return profile is not None and bool(profile.model and profile.api_key)

    def resolve_profile(self, profile_name: str | None = None) -> ModelProfile | None:
        if profile_name and profile_name in self.profiles:
            return self.profiles[profile_name]
        return self.profiles.get(self.default_profile)
