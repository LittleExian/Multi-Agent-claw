from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any

from openai import OpenAI
from pydantic import Field

from src.llm.config import LLMRuntimeConfig, ModelProfile
from src.shared.schemas import JSONDict, SwarmSchema


class ToolCallRequest(SwarmSchema):
    id: str
    name: str
    arguments_json: JSONDict = Field(default_factory=dict)
    raw_arguments_text: str = ""


class ChatTurnResult(SwarmSchema):
    model: str
    content: str = ""
    finish_reason: str | None = None
    tool_calls: list[ToolCallRequest] = Field(default_factory=list)
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    raw_assistant_message: JSONDict = Field(default_factory=dict)


class OpenAICompatibleClient:
    def __init__(self, config: LLMRuntimeConfig):
        self.config = config
        self._clients: dict[str, OpenAI] = {}

    def is_configured(self) -> bool:
        return self.config.is_configured()

    def complete(
        self,
        *,
        messages: Iterable[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        profile_name: str | None = None,
    ) -> ChatTurnResult:
        profile = self.config.resolve_profile(profile_name)
        if profile is None:
            raise RuntimeError("llm_profile_not_configured")

        client = self._client_for(profile)
        tool_payload = tools if tools and profile.supports_tools else None
        response = client.chat.completions.create(
            model=profile.model,
            messages=list(messages),
            tools=tool_payload,
            tool_choice="auto" if tool_payload else None,
            parallel_tool_calls=False if tool_payload else None,
            temperature=profile.temperature,
            max_tokens=profile.max_tokens,
            timeout=profile.timeout_seconds,
            extra_headers=profile.extra_headers or None,
        )
        choice = response.choices[0]
        message = choice.message
        usage = getattr(response, "usage", None)
        tool_calls = [
            ToolCallRequest(
                id=item.id,
                name=item.function.name,
                arguments_json=self._parse_arguments(item.function.arguments),
                raw_arguments_text=item.function.arguments or "",
            )
            for item in (message.tool_calls or [])
        ]
        raw_assistant_message: JSONDict = {
            "role": "assistant",
            "content": self._normalize_content(message.content) or None,
        }
        if tool_calls:
            raw_assistant_message["tool_calls"] = [
                {
                    "id": item.id,
                    "type": "function",
                    "function": {
                        "name": item.name,
                        "arguments": item.raw_arguments_text,
                    },
                }
                for item in tool_calls
            ]
        return ChatTurnResult(
            model=response.model or profile.model,
            content=self._normalize_content(message.content),
            finish_reason=choice.finish_reason,
            tool_calls=tool_calls,
            prompt_tokens=getattr(usage, "prompt_tokens", None),
            completion_tokens=getattr(usage, "completion_tokens", None),
            total_tokens=getattr(usage, "total_tokens", None),
            raw_assistant_message=raw_assistant_message,
        )

    @staticmethod
    def _normalize_content(content: Any) -> str:
        if content is None:
            return ""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                    continue
                if isinstance(item, dict) and item.get("type") == "text":
                    parts.append(str(item.get("text", "")))
            return "\n".join(part for part in parts if part)
        return str(content)

    @staticmethod
    def _parse_arguments(raw: str | None) -> JSONDict:
        if not raw:
            return {}
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {"_raw_arguments": raw}
        return parsed if isinstance(parsed, dict) else {"value": parsed}

    def _client_for(self, profile: ModelProfile) -> OpenAI:
        cache_key = profile.name
        if cache_key in self._clients:
            return self._clients[cache_key]
        kwargs: dict[str, Any] = {"api_key": profile.api_key}
        if profile.base_url:
            kwargs["base_url"] = profile.base_url
        client = OpenAI(**kwargs)
        self._clients[cache_key] = client
        return client
