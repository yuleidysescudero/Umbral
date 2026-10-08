"""Vuelca las etiquetas humanas de la vista «Etiquetar» a las hojas eval/labels/*.<snapshot>.csv.

Solo rellena `juicio_humano` y `comentario` de los ítems que una persona etiquetó (gana la etiqueta más reciente);
nunca inventa ni completa filas. Después se siguen los pasos de eval/labels/LEEME.md (import + métricas).

  python scripts/importar_etiquetas_mesa.py                          # desde la mesa compartida (Supabase)
  python scripts/importar_etiquetas_mesa.py --desde etiquetas.json   # desde el archivo descargado en modo local
  python scripts/importar_etiquetas_mesa.py --etiquetadores "Mesa editorial,Revisión"   # lista blanca de firmas

Integridad (QA TVN 3.11): la anon key está en el navegador, así que cualquier visitante podría insertar etiquetas.
Solo se aceptan las firmas de la lista blanca (--etiquetadores; por defecto los roles editoriales) y nunca el rol
Jurado; el script informa cuántas filas descartó y por qué.
Variables (solo en tu equipo, nunca en el repo): SUPABASE_URL y SUPABASE_SERVICE_ROLE_KEY.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import sys
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
HOJA = {"tema": "clasificacion", "par": "pares", "afirmacion": "afirmaciones"}


def desde_supabase() -> list[dict]:
    url, key = os.environ.get("SUPABASE_URL", "").rstrip("/"), os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not url or not key:
        sys.exit("Define SUPABASE_URL y SUPABASE_SERVICE_ROLE_KEY (o usa --desde <archivo>).")
    req = urllib.request.Request(f"{url}/rest/v1/etiquetas?producto=eq.umbral&select=*&order=created_at.asc",
                                 headers={"apikey": key, "Authorization": f"Bearer {key}"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--desde", type=Path, help="JSON descargado desde la vista Etiquetar")
    ap.add_argument("--etiquetadores", default="Mesa editorial,Producción digital,Revisión",
                    help="Firmas aceptadas, separadas por coma (columna persona)")
    a = ap.parse_args()
    permitidos = {x.strip() for x in a.etiquetadores.split(",") if x.strip()}
    snap = (RAIZ / "data" / "snapshots" / "CURRENT").read_text(encoding="utf-8").strip()
    filas = json.loads(a.desde.read_text(encoding="utf-8"))["etiquetas"] if a.desde else desde_supabase()
    ultima: dict[tuple[str, str], dict] = {}
    descartes: dict[str, int] = {}
    for f in filas:
        motivo = None
        if (f.get("rol") or "") == "jurado" or f.get("persona") == "Jurado hackIAthon":
            motivo = "rol Jurado"
        elif f.get("persona") not in permitidos:
            motivo = f"firma fuera de la lista blanca ({f.get('persona')!r})"
        elif len(str(f.get("comentario") or "")) > 500 or len(str(f.get("valor") or "")) > 60:
            motivo = "campo demasiado largo"
        if motivo:
            descartes[motivo] = descartes.get(motivo, 0) + 1
            continue
        ultima[(f["tipo"], f["item_id"])] = f
    print(f"Etiquetas leídas: {len(filas)} · aceptadas: {len(filas) - sum(descartes.values())} · descartadas: {sum(descartes.values())}")
    for motivo, n in sorted(descartes.items()):
        print(f"  descartadas por {motivo}: {n}")
    for tipo, nombre in HOJA.items():
        ruta = RAIZ / "eval" / "labels" / f"{nombre}.{snap}.csv"
        with open(ruta, encoding="utf-8-sig", newline="") as fh:
            lector = csv.DictReader(fh)
            cols, hoja = lector.fieldnames or [], list(lector)
        n = 0
        for r in hoja:
            e = ultima.get((tipo, r["id"]))
            if e:
                r["juicio_humano"] = e["valor"]
                r["comentario"] = (e.get("comentario") or "").strip() + (f" [{e['persona']}]" if e.get("persona") else "")
                n += 1
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=cols, lineterminator="\r\n")  # mismo formato que las hojas de make_label_sheets.py
        w.writeheader()
        w.writerows(hoja)
        ruta.write_bytes(("﻿" + buf.getvalue()).encode("utf-8"))
        print(f"  {ruta.name}: {n}/{len(hoja)} con juicio humano")
    print("Siguiente: eval/labels/LEEME.md → «Después de etiquetar» (import + métricas).")


if __name__ == "__main__":
    main()
