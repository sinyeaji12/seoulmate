from types import SimpleNamespace as NS

from seoulmate.clients.llm import to_openai_messages


def test_converts_tool_round_trip():
    msgs = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": [NS(type="tool_use", id="a", name="get_weather", input={"area": "종로"})]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "a", "content": "ok"}]},
    ]
    out = to_openai_messages("sys", msgs)
    assert out[0]["role"] == "system"
    assert out[2]["tool_calls"][0]["function"]["name"] == "get_weather"
    assert out[3] == {"role": "tool", "tool_call_id": "a", "content": "ok"}
