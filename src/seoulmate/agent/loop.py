"""LLM ↔ 도구 반복 루프. LLM 클라이언트와 레지스트리는 주입된다."""
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from seoulmate.agent.prompts import SYSTEM_PROMPT
from seoulmate.agent.schemas import Course, build_course
from seoulmate.tools.registry import ToolRegistry


class LLM(Protocol):
    def create(self, *, system: str, messages: list[dict], tools: list[dict]) -> Any:
        """Anthropic Messages 형식 응답(.stop_reason, .content[])을 반환."""


@dataclass
class AgentResult:
    answer: str
    tool_calls: list[dict] = field(default_factory=list)  # 평가·로깅용
    course: Course | None = None  # 형식 검증을 통과한 구조화 코스


REPEAT_FAILED = {
    "ok": False,
    "error": "이미 실패한 조회입니다. 이 항목은 '확인 불가'로 표시하고 다음으로 넘어가세요.",
}
WRAP_UP = "[시스템] 조회 가능한 횟수가 거의 끝났습니다. 더 호출하지 말고 지금까지 확인한 정보만으로 최종 JSON을 답하세요. 확인하지 못한 항목은 확인 불가로 쓰세요."


def run_agent(user_message: str, llm: LLM, registry: ToolRegistry, max_rounds: int = 6,
              on_tool: Callable[[dict], None] | None = None,
              enrich: Callable[[Course], Course] | None = None) -> AgentResult:
    messages: list[dict] = [{"role": "user", "content": user_message}]
    calls: list[dict] = []
    done: dict[tuple, dict] = {}  # 같은 호출은 다시 실행하지 않는다(실패 포함)
    for rnd in range(max_rounds):
        if rnd == max_rounds - 1 and rnd > 0 and isinstance(messages[-1]["content"], list):
            messages[-1]["content"].append({"type": "text", "text": WRAP_UP})
        resp = llm.create(system=SYSTEM_PROMPT, messages=messages, tools=registry.schemas())
        if resp.stop_reason != "tool_use":
            text = "".join(b.text for b in resp.content if b.type == "text")
            course = build_course(text, calls)
            return AgentResult(text, calls, enrich(course) if course and enrich else course)
        messages.append({"role": "assistant", "content": resp.content})
        results = []
        for b in resp.content:
            if b.type == "tool_use":
                sig = (b.name, json.dumps(b.input, sort_keys=True, ensure_ascii=False))
                if sig in done:
                    out = done[sig] if done[sig]["ok"] else REPEAT_FAILED
                else:
                    out = done[sig] = registry.call(b.name, b.input)
                calls.append({"name": b.name, "input": b.input, "result": out})
                if on_tool:
                    on_tool(calls[-1])
                results.append({"type": "tool_result", "tool_use_id": b.id, "content": str(out)})
        messages.append({"role": "user", "content": results})
    return AgentResult("죄송해요, 확인 단계가 너무 길어져 코스를 완성하지 못했어요.", calls)
