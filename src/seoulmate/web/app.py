"""얇은 웹 껍데기: 검증·스트리밍만 하고 로직은 agent에 맡긴다."""
import json
import queue
import threading
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from seoulmate.agent.enrich import make_enricher
from seoulmate.agent.loop import run_agent
from seoulmate.clients.llm import build_llm
from seoulmate.config import Settings, get_settings
from seoulmate.tools import build_registry
from seoulmate.web.security import RateLimiter

STATIC = Path(__file__).parent / "static"
limiter = RateLimiter()


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=500)


def create_app(settings: Settings | None = None, llm_factory=build_llm) -> FastAPI:
    s = settings or get_settings()
    app = FastAPI(title="서울 메이트")

    @app.get("/health")
    def health():
        return {"status": "ok", "mock_tools": s.seoulmate_mock_tools, "provider": s.llm_provider}

    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html")

    @app.post("/chat", dependencies=[Depends(limiter.check)])
    def chat(req: ChatRequest):
        message = req.message.strip()[: s.max_message_chars]
        events: queue.Queue = queue.Queue()

        def work():
            try:
                def on_tool(c):
                    events.put(("tool", {"name": c["name"], "input": c["input"], "ok": c["result"]["ok"]}))

                r = run_agent(message, llm_factory(s), build_registry(s), s.max_tool_rounds, on_tool,
                              make_enricher(s))
                events.put(("result", {"course": r.course.model_dump() if r.course else None,
                                       "answer": r.answer}))
            except Exception:  # noqa: BLE001 - 내부 오류·키는 클라이언트에 노출하지 않는다
                events.put(("error", {"message": "죄송해요, 지금은 코스를 만들지 못했어요. 잠시 후 다시 시도해 주세요."}))
            events.put(None)

        threading.Thread(target=work, daemon=True).start()

        def stream():
            while (item := events.get()) is not None:
                name, data = item
                yield f"event: {name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

        return StreamingResponse(stream(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    return app


app = create_app()
