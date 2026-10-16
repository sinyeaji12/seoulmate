"""얇은 웹 껍데기: 검증·스트리밍만 하고 로직은 agent에 맡긴다."""
import json
import queue
import threading
from pathlib import Path

from fastapi import Depends, FastAPI, Query
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from seoulmate.agent.enrich import make_enricher
from seoulmate.agent.gacha import SPOTS, spin
from seoulmate.agent.loop import run_agent
from seoulmate.clients.llm import build_llm
from seoulmate.clients.placeimg import ImageLookupError, PlaceImages
from seoulmate.config import Settings, get_settings
from seoulmate.tools import build_registry
from seoulmate.web.security import RateLimiter

STATIC = Path(__file__).parent / "static"
limiter = RateLimiter()
img_limiter = RateLimiter(limit=120)  # 코스 한 번에 사진 5장 안팎 → 채팅 한도와 분리
IMAGE_QUERIES = {sp["name"]: sp["image_query"] for sp in SPOTS if sp.get("image_query")}


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=500)


class GachaRequest(BaseModel):
    exclude: list[str] = Field(default_factory=list, max_length=10)  # 이미 뽑은 장소(다시 돌리기)


def create_app(settings: Settings | None = None, llm_factory=build_llm,
               images: PlaceImages | None = None) -> FastAPI:
    s = settings or get_settings()
    # 샘플 모드에서는 외부 호출을 하지 않는다(키를 비운 PlaceImages는 항상 '사진 없음')
    images = images or PlaceImages("" if s.seoulmate_mock_tools else s.tour_api_key)
    app = FastAPI(title="서울 메이트")
    app.mount("/static", StaticFiles(directory=STATIC), name="static")  # 표지 사진 등 정적 파일만

    @app.get("/health")
    def health():
        return {"status": "ok", "mock_tools": s.seoulmate_mock_tools, "provider": s.llm_provider}

    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html")

    @app.get("/place-image", dependencies=[Depends(img_limiter.check)])
    def place_image(name: str = Query(min_length=1, max_length=60)):
        """장소 대표 이미지를 백엔드가 대신 내려준다. 없으면 404(프론트가 플레이스홀더를 보여준다)."""
        try:
            got = images.fetch(name.strip(), IMAGE_QUERIES.get(name.strip()))
        except ImageLookupError:
            return Response(status_code=502, headers={"Cache-Control": "no-store"})
        if got is None:
            return Response(status_code=404, headers={"Cache-Control": "public, max-age=3600"})
        return Response(got[0], media_type=got[1],
                        headers={"Cache-Control": "public, max-age=86400, s-maxage=86400"})

    @app.post("/gacha", dependencies=[Depends(limiter.check)])
    def gacha(req: GachaRequest):
        try:
            return spin(build_registry(s), exclude=req.exclude).to_dict()
        except Exception:  # noqa: BLE001 - 내부 오류는 클라이언트에 노출하지 않는다
            return {"ok": False, "message": "앗, 가챠 기계가 잠깐 멈췄어. 다시 돌려줘!", "pick": None, "checked": []}

    @app.post("/gacha/stream", dependencies=[Depends(limiter.check)])
    def gacha_stream(req: GachaRequest):
        """/gacha와 같은 결과를, 날씨·혼잡도 도구가 호출되는 순간마다 tool 이벤트로 먼저 알려준다."""
        events: queue.Queue = queue.Queue()

        def work():
            try:
                r = spin(build_registry(s), exclude=req.exclude,
                         on_call=lambda c: events.put(("tool", {"name": c["name"], "ok": c["ok"]})))
                events.put(("result", r.to_dict()))
            except Exception:  # noqa: BLE001 - 내부 오류는 클라이언트에 노출하지 않는다
                events.put(("result", {"ok": False, "message": "앗, 가챠 기계가 잠깐 멈췄어. 다시 돌려줘!",
                                       "pick": None, "checked": [], "rejected": []}))
            events.put(None)

        threading.Thread(target=work, daemon=True).start()

        def stream():
            while (item := events.get()) is not None:
                yield f"event: {item[0]}\ndata: {json.dumps(item[1], ensure_ascii=False)}\n\n"

        return StreamingResponse(stream(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

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
