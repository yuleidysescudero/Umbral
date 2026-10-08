"""Vecinos semánticos precalculados para la recuperación multilingüe de consultas (QA TVN 3.4), sin tocar el snapshot.

La API no carga PyTorch (Vercel/Render): este script calcula fuera de línea los embeddings de cada titular con el mismo
modelo de scripts/agrupar_semantico.py (paraphrase-multilingual-MiniLM-L12-v2) y guarda, por artículo, sus vecinos más
parecidos (coseno). En la consulta, la API fusiona con reciprocal rank fusion (RRF) el ranking BM25 con el ranking de
vecinos semánticos de los mejores resultados: «32 tránsitos» (La Estrella) recupera «Daily Transits to 33» (inglés).

Escribe en data/agrupacion/<snapshotId>/:
  embeddings.f16.npy           matriz N×384 (float16, normalizada) en el orden de embeddings.ids.json
  embeddings.ids.json          IDs de artículo
  neighbors.semantic.jsonl     {"articleId", "neighbors": [[id, coseno], ...]}
  meta.vecinos.json            modelo, umbral, k y SHA-256 de cada archivo (la API verifica neighborsSha256)
Sin estos archivos la API cae a BM25 + RapidFuzz (T10 sin internet sigue funcionando).

  python scripts/vecinos_semanticos.py            # snapshot CURRENT
  python scripts/vecinos_semanticos.py --k 8 --umbral 0.6
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
from datetime import UTC, datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
MODELO = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
_PANAMA = re.compile(r"\b(rep[uú]blica de )?panam[aá]\b|\bpaname[ñn]\w*\b|\bpanamanian\b", re.I)


def sin_panama(t: str) -> str:
    return re.sub(r"\s+", " ", _PANAMA.sub(" ", t)).strip()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot", default=None, help="ID de snapshot (por defecto data/snapshots/CURRENT)")
    ap.add_argument("--k", type=int, default=8)
    ap.add_argument("--umbral", type=float, default=0.6)
    args = ap.parse_args()

    import numpy as np
    from sentence_transformers import SentenceTransformer

    snaps = RAIZ / "data" / "snapshots"
    sid = args.snapshot or (snaps / "CURRENT").read_text(encoding="utf-8").strip()
    rows = [json.loads(line) for line in (snaps / sid / "articles.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    ids = [r["articleId"] for r in rows]
    titles = [sin_panama(str(r.get("title", ""))) for r in rows]

    modelo = SentenceTransformer(MODELO, device="cpu")
    emb = modelo.encode(titles, batch_size=64, normalize_embeddings=True, show_progress_bar=False).astype("float32")
    sims = emb @ emb.T
    np.fill_diagonal(sims, -1.0)

    lines = []
    for i, aid in enumerate(ids):
        order = np.argsort(-sims[i])[: args.k]
        neigh = [[ids[j], round(float(sims[i, j]), 4)] for j in order if sims[i, j] >= args.umbral]
        lines.append(json.dumps({"articleId": aid, "neighbors": neigh}, ensure_ascii=False))
    texto = "\n".join(lines) + "\n"

    out = RAIZ / "data" / "agrupacion" / sid
    out.mkdir(parents=True, exist_ok=True)
    buf = io.BytesIO()
    np.save(buf, emb.astype("float16"))
    (out / "embeddings.f16.npy").write_bytes(buf.getvalue())
    ids_txt = json.dumps(ids, ensure_ascii=False)
    (out / "embeddings.ids.json").write_text(ids_txt, encoding="utf-8", newline="\n")
    (out / "neighbors.semantic.jsonl").write_bytes(texto.encode("utf-8"))
    meta = {
        "schemaVersion": 1,
        "snapshotId": sid,
        "generatedAt": datetime.now(UTC).isoformat(timespec="seconds"),
        "model": MODELO,
        "text": "titular sin la entidad «Panamá»",
        "k": args.k,
        "threshold": args.umbral,
        "fusion": "reciprocal rank fusion (k=60) entre BM25+RapidFuzz y vecinos semánticos de los mejores resultados",
        "neighborsSha256": hashlib.sha256(texto.encode("utf-8")).hexdigest(),
        "embeddingsSha256": hashlib.sha256(buf.getvalue()).hexdigest(),
        "idsSha256": hashlib.sha256(ids_txt.encode("utf-8")).hexdigest(),
        "articlesSha256": hashlib.sha256((snaps / sid / "articles.jsonl").read_bytes()).hexdigest(),
        "articles": len(ids),
        "withNeighbors": sum(1 for line in lines if '"neighbors": []' not in line),
    }
    (out / "meta.vecinos.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({k: meta[k] for k in ("snapshotId", "articles", "withNeighbors", "neighborsSha256")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
