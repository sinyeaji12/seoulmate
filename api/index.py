"""Vercel 진입점. src 레이아웃의 FastAPI 앱을 그대로 노출한다."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from seoulmate.web.app import app  # noqa: E402,F401
