"""Función de Vercel: sirve la API de Umbral (FastAPI) en el mismo dominio que la web, sin arranque en frío de Render.

Usa el snapshot verificado de data/snapshots/CURRENT empaquetado con la función; no escribe en disco.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "apps" / "api" / "src"))

actual = (RAIZ / "data" / "snapshots" / "CURRENT").read_text(encoding="utf-8").strip()
os.environ.setdefault("UMBRAL_SNAPSHOT_DIR", str(RAIZ / "data" / "snapshots" / actual))
os.environ.setdefault("UMBRAL_AUTH_MODE", "public")
os.environ.setdefault("UMBRAL_PERSISTENCE", "none")
os.environ.setdefault("UMBRAL_LOCAL_MODE", "0")
os.environ.setdefault("UMBRAL_SEMANTIC_CLUSTERS", "1")  # grupos semánticos de data/agrupacion (si los hashes cuadran)
os.environ.setdefault("UMBRAL_SCORING", "v2")  # QA TVN 3.9: normalización v2 (U continua, E +0,1 TVN/.gob.pa); v1 sigue disponible
os.environ.setdefault("UMBRAL_QUERIES_PER_MINUTE", "120")
os.environ.setdefault("UMBRAL_WEB_DIST", "/tmp/sin-dist")

from umbral_api.main import app  # noqa: E402

__all__ = ["app"]
