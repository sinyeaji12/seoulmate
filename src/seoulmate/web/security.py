import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request


class RateLimiter:
    """IP별 슬라이딩 윈도우. 단일 프로세스용 단순 구현."""

    def __init__(self, limit: int = 10, window: float = 60.0):
        self.limit, self.window = limit, window
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, request: Request) -> None:
        ip = request.client.host if request.client else "unknown"
        now, q = time.monotonic(), self._hits[ip]
        while q and now - q[0] > self.window:
            q.popleft()
        if len(q) >= self.limit:
            raise HTTPException(429, "요청이 너무 많아요. 잠시 후 다시 시도해 주세요.")
        q.append(now)
