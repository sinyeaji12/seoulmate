from types import SimpleNamespace as NS

import pytest

from seoulmate.config import Settings
from seoulmate.tools import build_registry


class FakeLLM:
    """미리 정한 응답을 순서대로 돌려주는 가짜 LLM."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.seen = []

    def create(self, *, system, messages, tools):
        self.seen.append(messages[:])
        return self.responses.pop(0)


def tool_use(name, input, id="t1"):
    return NS(stop_reason="tool_use", content=[NS(type="tool_use", name=name, input=input, id=id)])


def final(text):
    return NS(stop_reason="end_turn", content=[NS(type="text", text=text)])


@pytest.fixture
def registry():
    return build_registry(Settings(seoulmate_mock_tools=True))
