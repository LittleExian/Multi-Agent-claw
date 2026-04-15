from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class LangGraphCheckpointerHandle:
    backend: str
    checkpointer: Any
    db_path: Path | None = None
    _manager: AbstractContextManager[Any] | None = field(default=None, repr=False)

    def close(self) -> None:
        if self._manager is None:
            return
        self._manager.__exit__(None, None, None)
        self._manager = None


def build_sqlite_checkpointer(db_path: str | Path) -> LangGraphCheckpointerHandle:
    from langgraph.checkpoint.sqlite import SqliteSaver

    resolved = Path(db_path).expanduser().resolve()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    manager = SqliteSaver.from_conn_string(str(resolved))
    checkpointer = manager.__enter__()
    return LangGraphCheckpointerHandle(
        backend="sqlite",
        checkpointer=checkpointer,
        db_path=resolved,
        _manager=manager,
    )
