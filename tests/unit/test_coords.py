"""지도에 쓰는 좌표(lat/lng)가 TourAPI → 코스까지 전달되는지 확인한다."""
import json

import httpx

from seoulmate.agent.enrich import enrich_course
from seoulmate.agent.schemas import Course, Stop, build_course
from seoulmate.clients.tour import fetch_places


def _answer(*places):
    return json.dumps({"summary": "s", "stops": [{"time": "10:00", "place": p, "reason": "r"} for p in places]},
                      ensure_ascii=False)


def test_tour_client_passes_through_coordinates():
    item = {"title": "서울숲 곤충식물원", "addr1": "성동구", "contenttypeid": "12", "firstimage": "http://i/a.jpg",
            "mapy": "37.5431247707", "mapx": "127.0418131384"}
    bad = {"title": "좌표 없는 곳", "addr1": "서울", "contenttypeid": "12", "mapy": "", "mapx": None}
    body = {"response": {"header": {"resultCode": "0000"}, "body": {"items": {"item": [item, bad]}}}}
    client = httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200, json=body)))
    got = fetch_places("k", "12", keyword="coords-test", client=client)
    assert (got[0]["lat"], got[0]["lng"]) == (37.5431247707, 127.0418131384)
    assert got[1]["lat"] is None and got[1]["lng"] is None  # 없으면 지어내지 않는다


def test_course_stops_carry_coordinates_from_tool_results():
    calls = [{"name": "list_places", "input": {}, "result": {"ok": True, "data": [
        {"name": "서울숲 곤충식물원", "image": "", "lat": 37.54, "lng": 127.04}, {"name": "DDP", "image": ""}]}}]
    c = build_course(_answer("서울숲 곤충식물원", "DDP"), calls)
    assert (c.stops[0].lat, c.stops[0].lng) == (37.54, 127.04)
    assert c.stops[1].lat is None and c.stops[1].lng is None


def test_enrich_fills_missing_coordinates_but_keeps_existing_ones():
    catalog = [{"name": "북촌한옥마을", "content_type_id": "12", "image": "http://i/b.jpg", "lat": 37.58, "lng": 126.98}]
    c = Course(summary="s", stops=[
        Stop(time="1", place="북촌한옥마을", reason="r"),
        Stop(time="2", place="북촌한옥마을", reason="r", image="http://keep.jpg", lat=1.0, lng=2.0)])
    enrich_course(c, catalog)
    assert (c.stops[0].lat, c.stops[0].lng, c.stops[0].image) == (37.58, 126.98, "http://i/b.jpg")
    assert (c.stops[1].lat, c.stops[1].lng, c.stops[1].image) == (1.0, 2.0, "http://keep.jpg")


def test_enrich_adds_coordinates_even_when_photo_already_exists():
    catalog = [{"name": "북촌한옥마을", "content_type_id": "12", "image": "http://i/b.jpg", "lat": 37.58, "lng": 126.98}]
    c = Course(summary="s", stops=[Stop(time="1", place="북촌한옥마을", reason="r", image="http://has.jpg")])
    enrich_course(c, catalog)
    assert (c.stops[0].image, c.stops[0].lat) == ("http://has.jpg", 37.58)
