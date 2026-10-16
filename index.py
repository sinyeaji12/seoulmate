"""Vercel FastAPI 진입점. src 레이아웃의 앱을 그대로 노출한다(경로는 원래대로 유지)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from seoulmate.web.app import app  # noqa: E402,F401
