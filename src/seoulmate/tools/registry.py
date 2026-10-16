"""도구 등록·스키마 노출·실행 디스패치. 루프는 도구 구현을 모른다."""
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    input_schema: dict[str, Any]
    func: Callable[..., Any]


class ToolRegistry:
    def __init__(self, tools: list[Tool] | None = None):
        self._tools: dict[str, Tool] = {}
        for t in tools or []:
            self.register(t)

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def schemas(self) -> list[dict[str, Any]]:
        return [
            {"name": t.name, "description": t.description, "input_schema": t.input_schema}
            for t in self._tools.values()
        ]

    def call(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        """화이트리스트 밖 이름·실패는 예외 대신 오류 결과로 돌려 모델이 고지하게 한다."""
        tool = self._tools.get(name)
        if tool is None:
            return {"ok": False, "error": f"unknown tool: {name}"}
        try:
            return {"ok": True, "data": tool.func(**args)}
        except Exception as e:  # noqa: BLE001 - 도구 실패는 모델에 전달
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}
