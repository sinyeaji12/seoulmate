from seoulmate.agent.loop import run_agent
from tests.conftest import FakeLLM, final, tool_use


def test_calls_tools_before_answering(registry):
    llm = FakeLLM([tool_use("get_weather", {"area": "종로"}), final("실내 코스를 추천해요")])
    r = run_agent("오늘 어디 갈까?", llm, registry)
    assert [c["name"] for c in r.tool_calls] == ["get_weather"]
    assert r.answer == "실내 코스를 추천해요"


def test_unknown_tool_returns_error_not_crash(registry):
    llm = FakeLLM([tool_use("rm_rf", {}), final("확인하지 못했어요")])
    r = run_agent("x", llm, registry)
    assert r.tool_calls[0]["result"]["ok"] is False


def test_tool_failure_is_reported(registry):
    llm = FakeLLM([tool_use("get_weather", {"wrong": 1}), final("날씨를 확인하지 못했어요")])
    r = run_agent("x", llm, registry)
    assert r.tool_calls[0]["result"]["ok"] is False


def test_round_limit(registry):
    llm = FakeLLM([tool_use("list_places", {}, id=str(i)) for i in range(10)])
    r = run_agent("x", llm, registry, max_rounds=3)
    assert len(r.tool_calls) == 3
    assert "완성하지 못했" in r.answer


def test_repeated_failed_call_is_not_reexecuted(registry):
    calls = {"n": 0}
    orig = registry.call

    def counting(name, args):
        calls["n"] += 1
        return orig(name, args)

    registry.call = counting
    llm = FakeLLM([
        tool_use("get_weather", {"wrong": 1}, id="a"),
        tool_use("get_weather", {"wrong": 1}, id="b"),
        final("{}"),
    ])
    r = run_agent("x", llm, registry)
    assert calls["n"] == 1  # 두 번째는 실행하지 않고 캐시된 실패를 돌려줌
    assert r.tool_calls[1]["result"]["ok"] is False


def test_repeated_success_uses_cache(registry):
    llm = FakeLLM([tool_use("get_crowd", {"place": "서울숲"}, id="a"),
                   tool_use("get_crowd", {"place": "서울숲"}, id="b"), final("{}")])
    r = run_agent("x", llm, registry)
    assert r.tool_calls[0]["result"] == r.tool_calls[1]["result"]


def test_wrap_up_notice_sent_before_last_round(registry):
    llm = FakeLLM([tool_use("list_places", {}, id="a"), tool_use("get_crowd", {"place": "DDP"}, id="b"),
                   final("{}")])
    run_agent("x", llm, registry, max_rounds=3)
    last = llm.seen[-1][-1]["content"]
    assert any(isinstance(b, dict) and b.get("type") == "text" and "최종 JSON" in b["text"] for b in last)
