"""Exporta las hojas de etiquetado (eval/labels/*.<snapshot>.csv) a JSON para la vista web «Etiquetar».

Sin la columna `predicción`: se etiqueta a ciegas (LEEME.md, sesgo de anclaje). Para las afirmaciones se adjunta el
titular citado, que es lo que la persona debe comparar.
  python scripts/hojas_etiquetado.py
"""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]


def main() -> None:
    snap = (RAIZ / "data" / "snapshots" / "CURRENT").read_text(encoding="utf-8").strip()
    arts = {}
    for line in (RAIZ / "data" / "snapshots" / snap / "articles.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            a = json.loads(line)
            arts[a["articleId"]] = a

    def hoja(nombre: str) -> list[dict]:
        with open(RAIZ / "eval" / "labels" / f"{nombre}.{snap}.csv", encoding="utf-8-sig", newline="") as fh:
            return list(csv.DictReader(fh))

    tema = [{"id": r["id"], "texto": r["texto"], "medio": arts.get(r["id"], {}).get("outlet")} for r in hoja("clasificacion")]
    par = []
    for r in hoja("pares"):
        a, _, b = r["texto"].partition("  ||  ")
        par.append({"id": r["id"], "a": a.strip(), "b": b.strip()})
    afirmacion = []
    for r in hoja("afirmaciones"):
        m = re.search(r"\[cita:\s*([^/\]]+)/([^\]]+)\]", r["texto"])
        citado = arts.get(m.group(1), {}) if m else {}
        afirmacion.append({"id": r["id"], "texto": re.sub(r"\s*\[cita:[^\]]*\]", "", r["texto"]).strip(),
                           "cita": m.group(1) if m else None, "campo": m.group(2) if m else None,
                           "titularCitado": citado.get("title"), "medio": citado.get("outlet")})
    out = {"snapshotId": snap, "tema": tema, "par": par, "afirmacion": afirmacion}
    destino = RAIZ / "apps" / "web" / "public" / "etiquetado" / "hojas.json"
    destino.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print({k: len(v) for k, v in out.items() if isinstance(v, list)}, "→", destino.relative_to(RAIZ))


if __name__ == "__main__":
    main()
