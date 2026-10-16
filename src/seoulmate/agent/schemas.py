"""코스 응답 스키마. 모델은 시간·장소·이유만 내고, 사진·혼잡도는 도구 결과에서 서버가 채운다."""
import json
import re

from pydantic import BaseModel, ValidationError


class ModelStop(BaseModel):
    time: str
    place: str
    reason: str


class ModelCourse(BaseModel):
    summary: str
    stops: list[ModelStop]


class Stop(ModelStop):
    image: str = ""  # TourAPI firstimage. 없는 장소는 빈 문자열(화면에서 빈 값 처리)
    crowd: str = ""  # 조회하지 못했으면 빈 문자열
    crowd_next: str = ""  # 다음 시간 혼잡 예보
    category: str = ""  # outdoor | indoor | food | festival | ""(미확인)
    lat: float | None = None  # 지도용 좌표. TourAPI에 없는 장소는 None(지도에서 빠진다)
    lng: float | None = None


class Course(BaseModel):
    summary: str
    stops: list[Stop]
    weather: dict | None = None  # get_weather 결과 중 화면에 쓰는 값
    forecast: dict | None = None  # get_forecast 결과(내일·주말 질문일 때만). 없으면 None


def _extract_json(text: str) -> dict | None:
    text = re.sub(r"```(?:json)?", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None


def build_course(answer: str, tool_calls: list[dict]) -> Course | None:
    """모델 답변을 검증하고, 도구 결과로 사진·혼잡도를 채운다. 형식이 틀리면 None."""
    raw = _extract_json(answer)
    if raw is None:
        return None
    try:
        parsed = ModelCourse.model_validate(raw)
    except ValidationError:
        return None
    images: dict[str, str] = {}
    crowd: dict[str, str] = {}
    crowd_next: dict[str, str] = {}
    category: dict[str, str] = {}
    coords: dict[str, tuple[float, float]] = {}
    weather: dict | None = None
    forecast: dict | None = None
    for c in tool_calls:
        res = c["result"]
        if not res.get("ok"):
            continue
        data = res["data"]
        if c["name"] in ("list_places", "list_festivals"):
            for p in data:
                if p.get("image"):
                    images[p["name"]] = p["image"]
                category[p["name"]] = p.get("category") or ("festival" if c["name"] == "list_festivals" else "")
                if p.get("lat") is not None and p.get("lng") is not None:
                    coords[p["name"]] = (p["lat"], p["lng"])
        elif c["name"] == "get_crowd":
            crowd[data["place"]] = data["level"]
            crowd_next[data["place"]] = (data.get("next_hour") or {}).get("level") or ""
        elif c["name"] == "get_weather" and weather is None:
            weather = {k: data.get(k) for k in ("area", "temp_c", "precip", "pm10_grade")}
        elif c["name"] == "get_forecast" and forecast is None:
            forecast = {k: data.get(k) for k in ("district", "date", "when", "slots")}
    return Course(
        summary=parsed.summary,
        stops=[Stop(**s.model_dump(), image=images.get(s.place, ""), crowd=crowd.get(s.place, ""),
                    crowd_next=crowd_next.get(s.place, ""), category=category.get(s.place, ""),
                    lat=coords.get(s.place, (None, None))[0], lng=coords.get(s.place, (None, None))[1])
               for s in parsed.stops],
        weather=weather,
        forecast=forecast,
    )
