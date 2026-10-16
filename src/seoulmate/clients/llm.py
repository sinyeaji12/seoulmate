"""LLM 어댑터. 내부 표준은 Anthropic Messages 형식이며, OpenAI는 변환해서 맞춘다."""
import json
from types import SimpleNamespace as NS

import anthropic

from seoulmate.config import Settings


class AnthropicLLM:
    def __init__(self, api_key: str, model: str, workspace_id: str = ""):
        headers = {"anthropic-workspace-id": workspace_id} if workspace_id else None
        self._client = anthropic.Anthropic(api_key=api_key, timeout=30.0, default_headers=headers)
        self._model = model

    def create(self, *, system, messages, tools):
        return self._client.messages.create(
            model=self._model, max_tokens=1500, system=system, messages=messages, tools=tools
        )


def _blocks(content):
    return [b if isinstance(b, dict) else b.__dict__ for b in content]


def to_openai_messages(system: str, messages: list[dict]) -> list[dict]:
    out: list[dict] = [{"role": "system", "content": system}]
    for m in messages:
        if isinstance(m["content"], str):
            out.append({"role": m["role"], "content": m["content"]})
        elif m["role"] == "assistant":
            blocks = _blocks(m["content"])
            text = "".join(b["text"] for b in blocks if b["type"] == "text")
            calls = [
                {"id": b["id"], "type": "function",
                 "function": {"name": b["name"], "arguments": json.dumps(b["input"], ensure_ascii=False)}}
                for b in blocks if b["type"] == "tool_use"
            ]
            msg: dict = {"role": "assistant", "content": text or None}
            if calls:
                msg["tool_calls"] = calls
            out.append(msg)
        else:  # user 메시지 안의 tool_result들
            for b in _blocks(m["content"]):
                out.append({"role": "tool", "tool_call_id": b["tool_use_id"], "content": b["content"]})
    return out


class OpenAILLM:
    def __init__(self, api_key: str, model: str):
        import openai

        self._client = openai.OpenAI(api_key=api_key, timeout=30.0)
        self._model = model

    def create(self, *, system, messages, tools):
        oa_tools = [
            {"type": "function",
             "function": {"name": t["name"], "description": t["description"], "parameters": t["input_schema"]}}
            for t in tools
        ]
        resp = self._client.chat.completions.create(
            model=self._model, messages=to_openai_messages(system, messages), tools=oa_tools
        )
        msg = resp.choices[0].message
        content = []
        if msg.content:
            content.append(NS(type="text", text=msg.content))
        for c in msg.tool_calls or []:
            content.append(NS(type="tool_use", id=c.id, name=c.function.name,
                              input=json.loads(c.function.arguments or "{}")))
        stop = "tool_use" if msg.tool_calls else "end_turn"
        return NS(stop_reason=stop, content=content)


def build_llm(s: Settings):
    if s.llm_provider == "openai":
        return OpenAILLM(s.openai_api_key, s.resolved_model)
    return AnthropicLLM(s.anthropic_api_key, s.resolved_model, s.anthropic_workspace_id)
