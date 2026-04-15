from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path
from urllib.parse import quote_plus

import httpx
from pydantic import Field

from src.runtime.contracts import NodeExecutionContext
from src.shared.schemas import JSONDict, RiskLevel, SwarmSchema, ToolCategory
from src.tools.sandbox import LocalSandboxExecutor, SandboxExecutionResult


class ToolExecutionError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        timeout: bool = False,
        sandbox_result: SandboxExecutionResult | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.timeout = timeout
        self.sandbox_result = sandbox_result


class ToolExecutionContext(SwarmSchema):
    node: NodeExecutionContext
    workspace_root: str


class ToolExecutionResult(SwarmSchema):
    summary_text: str
    content_text: str
    structured_content: JSONDict = Field(default_factory=dict)
    sandbox_result: SandboxExecutionResult | None = None
    artifact_ids: list[str] = Field(default_factory=list)


class ToolDescriptor(SwarmSchema):
    name: str
    description: str
    category: ToolCategory
    risk_level: RiskLevel
    input_schema: JSONDict
    server_name: str | None = None
    sandbox_profile: str | None = None


class ToolRegistry:
    def __init__(
        self,
        *,
        workspace_root: str,
        sandbox_executor: LocalSandboxExecutor,
        browser_timeout_seconds: int = 15,
        max_read_chars: int = 12000,
    ):
        self.workspace_root = Path(workspace_root).resolve()
        self.sandbox_executor = sandbox_executor
        self.browser_timeout_seconds = browser_timeout_seconds
        self.max_read_chars = max_read_chars
        self._descriptors: dict[str, ToolDescriptor] = {}
        self._handlers: dict[str, Callable[[ToolExecutionContext, JSONDict], ToolExecutionResult]] = {}
        self._register_defaults()

    def list_openai_tools(self, names: list[str] | None = None) -> list[dict]:
        descriptors = self.list_descriptors(names)
        return [
            {
                "type": "function",
                "function": {
                    "name": descriptor.name,
                    "description": descriptor.description,
                    "parameters": descriptor.input_schema,
                },
            }
            for descriptor in descriptors
        ]

    def list_descriptors(self, names: list[str] | None = None) -> list[ToolDescriptor]:
        if not names:
            return list(self._descriptors.values())
        result: list[ToolDescriptor] = []
        seen: set[str] = set()
        for name in names:
            if name in self._descriptors and name not in seen:
                result.append(self._descriptors[name])
                seen.add(name)
        return result

    def get_descriptor(self, name: str) -> ToolDescriptor:
        if name not in self._descriptors:
            raise ToolExecutionError("tool.not_found", f"Unsupported tool: {name}")
        return self._descriptors[name]

    def execute(self, name: str, arguments_json: JSONDict, context: ToolExecutionContext) -> ToolExecutionResult:
        if name not in self._handlers:
            raise ToolExecutionError("tool.not_found", f"Unsupported tool: {name}")
        return self._handlers[name](context, arguments_json)

    def _register(
        self,
        descriptor: ToolDescriptor,
        handler: Callable[[ToolExecutionContext, JSONDict], ToolExecutionResult],
    ) -> None:
        self._descriptors[descriptor.name] = descriptor
        self._handlers[descriptor.name] = handler

    def _register_defaults(self) -> None:
        self._register(
            ToolDescriptor(
                name="filesystem.list_dir",
                description="List files and directories relative to the workspace root.",
                category=ToolCategory.BUILTIN,
                risk_level=RiskLevel.READ,
                input_schema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "default": "."},
                    },
                    "required": [],
                    "additionalProperties": False,
                },
            ),
            self._list_dir,
        )
        self._register(
            ToolDescriptor(
                name="filesystem.read_file",
                description="Read a UTF-8 text file from the workspace.",
                category=ToolCategory.BUILTIN,
                risk_level=RiskLevel.READ,
                input_schema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "start_line": {"type": "integer", "minimum": 1},
                        "end_line": {"type": "integer", "minimum": 1},
                    },
                    "required": ["path"],
                    "additionalProperties": False,
                },
            ),
            self._read_file,
        )
        self._register(
            ToolDescriptor(
                name="filesystem.write_file",
                description="Write UTF-8 text content into a workspace file.",
                category=ToolCategory.BUILTIN,
                risk_level=RiskLevel.MUTABLE,
                input_schema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "content": {"type": "string"},
                        "append": {"type": "boolean", "default": False},
                    },
                    "required": ["path", "content"],
                    "additionalProperties": False,
                },
            ),
            self._write_file,
        )
        self._register(
            ToolDescriptor(
                name="shell.exec",
                description="Run a shell command inside the local subprocess sandbox.",
                category=ToolCategory.SANDBOXED,
                risk_level=RiskLevel.MUTABLE,
                input_schema={
                    "type": "object",
                    "properties": {
                        "command": {"type": "string"},
                        "cwd": {"type": "string"},
                        "timeout_seconds": {"type": "integer", "minimum": 1},
                    },
                    "required": ["command"],
                    "additionalProperties": False,
                },
                sandbox_profile="local-subprocess",
            ),
            self._shell_exec,
        )
        self._register(
            ToolDescriptor(
                name="browser.fetch",
                description="Fetch the text content of an HTTP URL.",
                category=ToolCategory.BUILTIN,
                risk_level=RiskLevel.READ,
                input_schema={
                    "type": "object",
                    "properties": {
                        "url": {"type": "string"},
                    },
                    "required": ["url"],
                    "additionalProperties": False,
                },
            ),
            self._browser_fetch,
        )
        self._register(
            ToolDescriptor(
                name="browser.search",
                description="Search the web and return a small set of results.",
                category=ToolCategory.BUILTIN,
                risk_level=RiskLevel.READ,
                input_schema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "num_results": {"type": "integer", "minimum": 1, "maximum": 10, "default": 5},
                    },
                    "required": ["query"],
                    "additionalProperties": False,
                },
            ),
            self._browser_search,
        )

    def _list_dir(self, context: ToolExecutionContext, arguments_json: JSONDict) -> ToolExecutionResult:
        target = self._resolve_workspace_path(str(arguments_json.get("path", ".")))
        if not target.exists():
            raise ToolExecutionError("filesystem.not_found", f"Path does not exist: {target}")
        if not target.is_dir():
            raise ToolExecutionError("filesystem.not_directory", f"Path is not a directory: {target}")
        entries = [
            {
                "name": item.name,
                "path": str(item.relative_to(self.workspace_root)),
                "is_dir": item.is_dir(),
            }
            for item in sorted(target.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower()))
        ]
        return ToolExecutionResult(
            summary_text=f"Listed {len(entries)} entries under {target.relative_to(self.workspace_root)}.",
            content_text=json.dumps(entries, ensure_ascii=False, indent=2),
            structured_content={"entries": entries},
        )

    def _read_file(self, context: ToolExecutionContext, arguments_json: JSONDict) -> ToolExecutionResult:
        target = self._resolve_workspace_path(str(arguments_json["path"]))
        if not target.exists():
            raise ToolExecutionError("filesystem.not_found", f"File does not exist: {target}")
        if not target.is_file():
            raise ToolExecutionError("filesystem.not_file", f"Path is not a file: {target}")
        text = target.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        start_line = int(arguments_json.get("start_line", 1))
        end_line = int(arguments_json.get("end_line", len(lines))) if lines else start_line
        sliced = "\n".join(lines[start_line - 1 : end_line])
        clipped = sliced[: self.max_read_chars]
        return ToolExecutionResult(
            summary_text=f"Read {target.relative_to(self.workspace_root)} lines {start_line}-{end_line}.",
            content_text=clipped,
            structured_content={
                "path": str(target.relative_to(self.workspace_root)),
                "start_line": start_line,
                "end_line": end_line,
                "truncated": len(sliced) > len(clipped),
            },
        )

    def _write_file(self, context: ToolExecutionContext, arguments_json: JSONDict) -> ToolExecutionResult:
        target = self._resolve_workspace_path(str(arguments_json["path"]))
        if target.exists() and target.is_dir():
            raise ToolExecutionError("filesystem.not_file", f"Path is a directory: {target}")
        target.parent.mkdir(parents=True, exist_ok=True)
        append = bool(arguments_json.get("append", False))
        content = str(arguments_json["content"])
        mode = "a" if append else "w"
        with target.open(mode, encoding="utf-8") as handle:
            handle.write(content)
        return ToolExecutionResult(
            summary_text=f"Wrote {len(content)} characters to {target.relative_to(self.workspace_root)}.",
            content_text=f"ok: wrote {target.relative_to(self.workspace_root)}",
            structured_content={
                "path": str(target.relative_to(self.workspace_root)),
                "append": append,
                "chars_written": len(content),
            },
        )

    def _shell_exec(self, context: ToolExecutionContext, arguments_json: JSONDict) -> ToolExecutionResult:
        command = str(arguments_json["command"])
        cwd = arguments_json.get("cwd")
        timeout_seconds = int(arguments_json.get("timeout_seconds", self.sandbox_executor.default_timeout_seconds))
        try:
            sandbox_result = self.sandbox_executor.run_shell(
                command=command,
                cwd=str(cwd) if cwd is not None else None,
                timeout_seconds=timeout_seconds,
            )
        except ValueError as exc:
            raise ToolExecutionError("sandbox.invalid_cwd", str(exc)) from exc
        if sandbox_result.timed_out:
            raise ToolExecutionError(
                "sandbox.timeout",
                f"Shell command timed out after {timeout_seconds}s.",
                timeout=True,
                sandbox_result=sandbox_result,
            )
        if sandbox_result.exit_code not in {0, None}:
            raise ToolExecutionError(
                "sandbox.non_zero_exit",
                f"Shell command exited with code {sandbox_result.exit_code}.",
                sandbox_result=sandbox_result,
            )
        content = sandbox_result.stdout_excerpt or ""
        if sandbox_result.stderr_excerpt:
            content = f"{content}\n{sandbox_result.stderr_excerpt}".strip()
        return ToolExecutionResult(
            summary_text="Shell command completed successfully.",
            content_text=content[:4000],
            structured_content={
                "exit_code": sandbox_result.exit_code,
                "stdout_excerpt": sandbox_result.stdout_excerpt,
                "stderr_excerpt": sandbox_result.stderr_excerpt,
            },
            sandbox_result=sandbox_result,
        )

    def _browser_fetch(self, context: ToolExecutionContext, arguments_json: JSONDict) -> ToolExecutionResult:
        url = str(arguments_json["url"])
        try:
            response = httpx.get(
                url,
                timeout=self.browser_timeout_seconds,
                follow_redirects=True,
                headers={"user-agent": "Multi-Agent-Claw/0.1"},
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ToolExecutionError("browser.fetch_failed", f"Failed to fetch {url}: {exc}") from exc
        text = response.text[: self.max_read_chars]
        return ToolExecutionResult(
            summary_text=f"Fetched {url}.",
            content_text=text,
            structured_content={
                "url": url,
                "status_code": response.status_code,
                "content_type": response.headers.get("content-type"),
                "truncated": len(response.text) > len(text),
            },
        )

    def _browser_search(self, context: ToolExecutionContext, arguments_json: JSONDict) -> ToolExecutionResult:
        query = str(arguments_json["query"])
        num_results = int(arguments_json.get("num_results", 5))
        url = f"https://duckduckgo.com/html/?q={quote_plus(query)}"
        try:
            response = httpx.get(
                url,
                timeout=self.browser_timeout_seconds,
                follow_redirects=True,
                headers={"user-agent": "Multi-Agent-Claw/0.1"},
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ToolExecutionError("browser.search_failed", f"Failed to search for '{query}': {exc}") from exc
        results = []
        for match in re.finditer(r'<a[^>]*class=\"result__a\"[^>]*href=\"([^\"]+)\"[^>]*>(.*?)</a>', response.text, re.IGNORECASE | re.DOTALL):
            href = re.sub(r"&amp;", "&", match.group(1))
            title = re.sub(r"<[^>]+>", "", match.group(2)).strip()
            if title:
                results.append({"title": title, "url": href})
            if len(results) >= num_results:
                break
        return ToolExecutionResult(
            summary_text=f"Found {len(results)} search results for '{query}'.",
            content_text=json.dumps(results, ensure_ascii=False, indent=2),
            structured_content={"query": query, "results": results},
        )

    def _resolve_workspace_path(self, raw_path: str) -> Path:
        candidate = (
            (self.workspace_root / raw_path).resolve()
            if not Path(raw_path).is_absolute()
            else Path(raw_path).resolve()
        )
        if not candidate.is_relative_to(self.workspace_root):
            raise ToolExecutionError("filesystem.outside_workspace", f"Path is outside workspace: {raw_path}")
        return candidate
