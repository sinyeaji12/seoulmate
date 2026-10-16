"""'오늘의 서울' 지면: 산책지 후보의 현재 혼잡도를 기존 get_crowd 도구로 모아 한산한 곳 / 붐비는 곳으로 나눈다.

새 데이터를 만들지 않는다 — 모든 값은 ToolRegistry의 get_crowd 결과이고, 도구가 실패한 후보는 조용히 빠진다.
후보는 가챠가 쓰는 산책지(서울시가 실제로 응답하는 지역명으로만 구성)를 그대로 쓴다.
"""
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

from seoulmate.agent.gacha import RANK, SPOTS
from seoulmate.tools.registry import ToolRegistry

MAX_EACH = 3
CALM = {"여유"}
BUSY_ORDER = {"붐빔": 0, "약간 붐빔": 1}  # 더 붐비는 단계가 먼저. 같은 단계는 후보 목록 순서(도구가 인구 수치를 주지 않는다)


def snapshot(registry: ToolRegistry, spots: list[dict] | None = None, *, workers: int = 6, limit: int = MAX_EACH) -> dict:
    spots = SPOTS if spots is None else spots

    def one(spot: dict) -> dict:
        return registry.call("get_crowd", {"place": spot["area"]})

    with ThreadPoolExecutor(workers) as ex:
        outs = list(ex.map(one, spots))  # 결과 순서는 후보 순서 그대로

    rows = []
    for idx, (spot, out) in enumerate(zip(spots, outs)):
        data = out.get("data") if out.get("ok") else None
        if not data or data.get("level") not in RANK:
            continue  # 조회에 실패한 곳은 값을 짐작하지 않고 뺀다
        rows.append({"idx": idx, "name": spot["name"], "level": data["level"], "observed_at": data.get("observed_at", "")})

    calm = [r for r in rows if r["level"] in CALM][:limit]
    busy = sorted((r for r in rows if r["level"] in BUSY_ORDER), key=lambda r: (BUSY_ORDER[r["level"]], r["idx"]))[:limit]
    # 기준 시각: 화면에 나오는 곳들 중 가장 오래된 관측 시각(전부 이 시각 이후의 값이다)
    stamps = sorted(r["observed_at"] for r in (*calm, *busy) if r["observed_at"])
    date, _, hhmm = stamps[0].partition(" ") if stamps else ("", "", "")
    return {
        "ok": bool(rows),
        "observed_at": hhmm[:5], "observed_date": date,
        "calm": [{"name": r["name"], "level": r["level"]} for r in calm],
        "busy": [{"name": r["name"], "level": r["level"]} for r in busy],
        "checked": len(rows), "total": len(spots),
    }


class SeoulNow:
    """snapshot 결과를 잠시 캐싱한다(외부 API 호출 수를 줄이기 위해). 실패 결과는 캐싱하지 않는다."""

    def __init__(self, registry_factory: Callable[[], ToolRegistry], *, enabled: bool = True, ttl: float = 300.0,
                 spots: list[dict] | None = None, clock: Callable[[], float] = time.monotonic):
        self._factory, self._enabled, self._ttl, self._spots, self._clock = registry_factory, enabled, ttl, spots, clock
        self._lock = threading.Lock()
        self._value: dict | None = None
        self._at = 0.0

    def get(self) -> dict:
        if not self._enabled:  # 샘플 모드의 고정 값을 '실시간'으로 보여 주지 않는다
            return {"ok": False, "reason": "sample_mode"}
        with self._lock:  # 동시 요청이 와도 외부 호출은 한 번만
            if self._value is not None and self._clock() - self._at < self._ttl:
                return self._value
            try:
                value = snapshot(self._factory(), self._spots)
            except Exception:  # noqa: BLE001 - 지면은 부가 정보라 실패해도 다른 기능에 영향이 없어야 한다
                return {"ok": False, "reason": "unavailable"}
            if value["ok"]:
                self._value, self._at = value, self._clock()
            return value
