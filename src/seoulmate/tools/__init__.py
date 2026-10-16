from functools import partial

from seoulmate.clients.seoul import SUPPORTED_AREAS
from seoulmate.config import Settings
from seoulmate.tools.crowd import get_crowd
from seoulmate.tools.festivals import list_festivals
from seoulmate.tools.forecast import get_forecast
from seoulmate.tools.places import list_places
from seoulmate.tools.registry import Tool, ToolRegistry
from seoulmate.tools.weather import get_weather


def build_registry(s: Settings) -> ToolRegistry:
    kw = {"mock": s.seoulmate_mock_tools, "api_key": s.seoul_api_key}
    tour_kw = {"mock": s.seoulmate_mock_tools, "api_key": s.tour_api_key}
    kma_kw = {"mock": s.seoulmate_mock_tools, "api_key": s.kma_api_key or s.tour_api_key}  # 공공데이터포털 키는 계정 단위
    return ToolRegistry([
        Tool("get_weather", "서울 주요 장소의 현재 날씨(기온·강수·미세먼지)를 조회한다. area는 get_crowd와 같은 지원 장소명이어야 하며 '서울' 같은 총칭은 불가.",
             {"type": "object", "properties": {"area": {"type": "string"}}, "required": ["area"]},
             partial(get_weather, **kw)),
        Tool("get_crowd", "특정 장소의 현재 혼잡도를 조회한다. place는 다음 지원 장소명만 가능: "
             + ", ".join(SUPPORTED_AREAS),
             {"type": "object", "properties": {"place": {"type": "string"}}, "required": ["place"]},
             partial(get_crowd, **kw)),
        Tool("list_places", "나들이 후보 장소 목록(한국관광공사). category: indoor|outdoor|food(음식점)|all. "
             "keyword로 검색, district(예: 종로구)로 구 단위 필터. 식당은 category=food + district로 찾는다.",
             {"type": "object", "properties": {"category": {"type": "string",
              "enum": ["indoor", "outdoor", "food", "all"]}, "keyword": {"type": "string"},
              "district": {"type": "string"}}},
             partial(list_places, **tour_kw)),
        Tool("get_forecast", "내일·주말 등 앞날의 날씨 예보(기상청 단기예보). district는 서울 구 이름(예: 성동구), "
             "when은 today|tomorrow|saturday|sunday. 오전·오후·저녁별 기온·강수확률·하늘상태를 준다. "
             "예보는 며칠 앞까지만 있어 범위 밖이면 오류가 나며, 그때는 확인 불가로 알린다.",
             {"type": "object", "properties": {"district": {"type": "string"},
              "when": {"type": "string", "enum": ["today", "tomorrow", "saturday", "sunday"]}},
              "required": ["district", "when"]},
             partial(get_forecast, **kma_kw)),
        Tool("list_festivals", "오늘 서울에서 진행 중인 행사·축제 목록(한국관광공사). 없으면 빈 목록.",
             {"type": "object", "properties": {}},
             partial(list_festivals, **tour_kw)),
    ])
