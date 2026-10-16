import sys

from seoulmate.agent.enrich import make_enricher
from seoulmate.agent.loop import run_agent
from seoulmate.clients.llm import build_llm
from seoulmate.config import get_settings
from seoulmate.tools import build_registry

s = get_settings()
q = " ".join(sys.argv[1:]) or "오늘 서울 어디 갈까?"
r = run_agent(q, build_llm(s), build_registry(s), s.max_tool_rounds, enrich=make_enricher(s))
for c in r.tool_calls:
    print(f"[tool] {c['name']}({c['input']}) -> ok={c['result']['ok']}", file=sys.stderr)
if r.course:
    print(r.course.summary)
    for st in r.course.stops:
        print(f"{st.time} {st.place} [{st.crowd or '혼잡도 미확인'}] {st.reason}")
else:
    print(r.answer)
