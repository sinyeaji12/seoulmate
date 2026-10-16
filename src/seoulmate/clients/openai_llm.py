"""OpenAI 어댑터. 루프가 쓰는 Anthropic식 메시지/응답 형식으로 변환한다."""
import json
from types import SimpleNamespace as NS

from openai import OpenAI


def _get(b, k):
    return b[k] if isinstance(b, dict) else getattr(b, k)


class OpenAILLM:
    def __init__(self, api_key: str, model: str):
        self._client = OpenAI(api_key=api_key, timeout=30.0)
        self._model = model

    def create(self, *, system, messages, tools):
        oa_tools = [
            {"type": "function", "function": {
                "name": t["name"], "description": t["description"], "parameters": t["input_schema"]}}
            for t in tools
        ]
        r = self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": "system", "content": system}, *self._convert(messages)],
            tools=oa_tools,
        )
        msg = r.choices[0].message
        blocks = []
        if msg.content:
            blocks.append(NS(type="text", text=msg.content))
        for tc in msg.tool_calls or []:
            blocks.append(NS(type="tool_use", id=tc.id, name=tc.function.name,
                             input=json.loads(tc.function.arguments or "{}")))
        uses_tools = any(b.type == "tool_use" for b in blocks)
        return NS(stop_reason="tool_use" if uses_tools else "end_turn", content=blocks)

    @staticmethod
    def _convert(messages):
        out = []
        for m in messages:
            c = m["content"]
            if isinstance(c, str):
                out.append({"role": m["role"], "content": c})
            elif m["role"] == "assistant":
                text = "".join(_get(b, "text") for b in c if _get(b, "type") == "text")
                calls = [{"id": _get(b, "id"), "type": "function", "function": {
                    "name": _get(b, "name"), "arguments": json.dumps(_get(b, "input"), ensure_ascii=False)}}
                    for b in c if _get(b, "type") == "tool_use"]
                out.append({"role": "assistant", "content": text or None, "tool_calls": calls})
            else:
                for b in c:
                    out.append({"role": "tool", "tool_call_id": b["tool_use_id"], "content": b["content"]})
        return out
