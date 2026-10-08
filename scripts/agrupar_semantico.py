"""Agrupación semántica de eventos sobre un snapshot verificado (CU-03), sin tocar el snapshot.

El pipeline une solo titulares casi idénticos (token_sort_ratio >= 88): las paráfrasis («Economía de Panamá crece
5,5 %» / «PIB panameño aumentó 5,5 % en el semestre») y las versiones en otro idioma quedan como temas sueltos, la
agenda se llena de temas de una sola nota y la corroboración independiente casi nunca aparece.

Este script une GRUPOS del snapshot cuando algún par de sus titulares es semánticamente equivalente:
  - embeddings multilingües (sentence-transformers, paraphrase-multilingual-MiniLM-L12-v2, CPU),
  - sobre el titular sin la entidad omnipresente «Panamá» (si no, todo se parece a todo),
  - similitud coseno >= UMBRAL y fechas a <= VENTANA_H horas,
y escribe data/agrupacion/<snapshotId>/clusters.semantic.jsonl + meta.json (SHA-256, parámetros, muestra de uniones).
La API lo usa si existe; si no, usa clusters.jsonl tal cual. Requiere PyTorch: se ejecuta fuera de línea, no en la API.

  python scripts/agrupar_semantico.py                       # snapshot CURRENT
  python scripts/agrupar_semantico.py --umbral 0.72 --ventana-h 72
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "pipeline"))
from umbral_pipeline.cluster import UF, independent_provenance, norm_title, numbers_conflict, numbers_in, tokens  # noqa: E402

MODELO = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
_PANAMA = re.compile(r"\b(rep[uú]blica de )?panam[aá]\b|\bpaname[ñn]\w*\b|\bpanamanian\b", re.I)


def sin_panama(t: str) -> str:
    return re.sub(r"\s+", " ", _PANAMA.sub(" ", t)).strip()


_GENERICAS = {"panama", "panameno", "panamena", "panamenos", "panamanian", "colombia", "mexico", "guatemala", "costa", "rica",
              "dominicana", "venezuela", "ecuador", "nuevo", "nueva", "dia", "hoy", "ano", "anos", "2026", "2025"}


def anclas(t: str) -> set[str]:
    """Palabras de contenido (raíz de 5 letras), sin países ni palabras comodín."""
    return {w[:5] for w in tokens(t) if w not in _GENERICAS and not w.isdigit() and len(w) > 3}


def fecha(a: dict) -> datetime | None:
    v = a.get("publishedAt") or a.get("effectiveDate") or a.get("detectedAt")
    return datetime.fromisoformat(v.replace("Z", "+00:00")) if v else None


def leer(p: Path) -> list[dict]:
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot", default=None)
    ap.add_argument("--umbral", type=float, default=0.74)
    ap.add_argument("--alta", type=float, default=0.84, help="desde aquí basta la similitud; debajo se exige anclaje léxico")
    ap.add_argument("--anclaje", type=int, default=2, help="palabras de contenido compartidas exigidas bajo --alta")
    ap.add_argument("--ventana-h", type=float, default=72)
    a = ap.parse_args()
    snap_id = a.snapshot or (RAIZ / "data" / "snapshots" / "CURRENT").read_text(encoding="utf-8").strip()
    snap = RAIZ / "data" / "snapshots" / snap_id
    arts = leer(snap / "articles.jsonl")
    clusters = leer(snap / "clusters.jsonl")
    by_id = {x["articleId"]: x for x in arts}
    cl_de = {m: c["clusterId"] for c in clusters for m in c["memberArticleIds"]}

    from sentence_transformers import SentenceTransformer

    modelo = SentenceTransformer(MODELO, device="cpu")
    ids = [x["articleId"] for x in arts]
    emb = modelo.encode([sin_panama(by_id[i]["title"]) for i in ids], batch_size=64, normalize_embeddings=True,
                        show_progress_bar=False)
    sims = emb @ emb.T
    fechas = [fecha(by_id[i]) for i in ids]
    anc = [anclas(by_id[i]["title"]) for i in ids]

    uf = UF([c["clusterId"] for c in clusters])
    uniones: list[dict] = []
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            s = float(sims[i, j])
            if s < a.umbral:
                continue
            if s < a.alta and len(anc[i] & anc[j]) < a.anclaje:
                continue  # parecido temático, no el mismo hecho
            ci, cj = cl_de[ids[i]], cl_de[ids[j]]
            if uf.find(ci) == uf.find(cj):
                continue
            fi, fj = fechas[i], fechas[j]
            if fi and fj and abs((fi - fj).total_seconds()) / 3600 > a.ventana_h:
                continue
            uf.union(ci, cj)
            uniones.append({"a": ids[i], "b": ids[j], "method": "semantic_embedding", "score": round(s, 4)})

    grupos: dict[str, list[dict]] = defaultdict(list)
    for c in clusters:
        grupos[uf.find(c["clusterId"])].append(c)

    salida = []
    for partes in grupos.values():
        if len(partes) == 1:
            salida.append(partes[0])
            continue
        miembros = sorted({m for c in partes for m in c["memberArticleIds"]}, key=lambda m: (by_id[m]["effectiveDate"] or "", m))
        mset = set(miembros)
        sel = [by_id[m] for m in miembros]
        # Representante: el titular en español publicado primero (la mesa es de TVN); si no hay, el más antiguo.
        con_fecha = [x for x in sel if x.get("publishedAt")]
        es = [x for x in con_fecha if x.get("language") == "es"] or con_fecha or sel
        rep = min(es, key=lambda x: (x.get("publishedAt") or "~", x["articleId"]))
        normed = {x["articleId"]: norm_title(x["title"]) for x in sel}
        votos: Counter[str] = Counter()
        for c in partes:
            if c.get("category") and c["category"] != "indeterminado":
                votos[c["category"]] += c["size"]
        nums = [numbers_in(x["title"]) for x in sel]
        contradiccion = any(numbers_conflict(p, q) for k, p in enumerate(nums) for q in nums[k + 1:])
        pubs = sorted(x["publishedAt"] for x in sel if x.get("publishedAt"))
        links = [lk for c in partes for lk in c.get("links", [])] + [u for u in uniones if u["a"] in mset and u["b"] in mset]
        recirc = next((c for c in partes if c.get("isRecirculation")), None)
        salida.append({
            **partes[0],
            "clusterId": "evt_" + hashlib.sha256("|".join(sorted(miembros)).encode()).hexdigest()[:16],
            "memberArticleIds": miembros,
            "representativeArticleId": rep["articleId"],
            "size": len(miembros),
            "category": max(votos, key=lambda k: (votos[k], k)) if votos else "indeterminado",
            "provenanceKeys": sorted({k for c in partes for k in c.get("provenanceKeys", [])}),
            "independentProvenanceCount": independent_provenance(sel, normed),
            "outletCount": len({x["domain"] for x in sel}),
            "links": links,
            "ambiguous": any(c.get("ambiguous") for c in partes),
            "ambiguousCandidateIds": sorted({k for c in partes for k in c.get("ambiguousCandidateIds", []) if k not in mset}),
            "firstPublishedAt": pubs[0] if pubs else None,
            "lastPublishedAt": pubs[-1] if pubs else None,
            "originalPublishedAt": pubs[0] if pubs else None,
            "isRecirculation": recirc is not None,
            "recirculationReason": recirc.get("recirculationReason") if recirc else None,
            "hasContradictionCandidate": contradiccion or any(c.get("hasContradictionCandidate") for c in partes),
            "contradictionCandidateIds": sorted({k for c in partes for k in c.get("contradictionCandidateIds", []) if k not in mset}),
            "mergedFromClusterIds": sorted(c["clusterId"] for c in partes),
        })
    salida.sort(key=lambda c: (c["memberArticleIds"][0], c["clusterId"]))

    out = RAIZ / "data" / "agrupacion" / snap_id
    out.mkdir(parents=True, exist_ok=True)
    texto = "".join(json.dumps(c, ensure_ascii=False, separators=(",", ":")) + "\n" for c in salida)
    (out / "clusters.semantic.jsonl").write_bytes(texto.encode("utf-8"))
    multi = [c for c in salida if c["size"] > 1]
    meta = {
        "schemaVersion": 1, "snapshotId": snap_id, "generatedAt": datetime.now(UTC).isoformat(timespec="seconds"),
        "method": "semantic_embedding", "model": MODELO, "threshold": a.umbral, "highThreshold": a.alta,
        "lexicalAnchor": a.anclaje, "windowHours": a.ventana_h,
        "text": "titular sin la entidad «Panamá»",
        "clustersSha256": hashlib.sha256(texto.encode("utf-8")).hexdigest(),
        "sourceClustersSha256": hashlib.sha256((snap / "clusters.jsonl").read_bytes()).hexdigest(),
        "counts": {"articles": len(arts), "clustersBefore": len(clusters), "clustersAfter": len(salida),
                   "semanticLinks": len(uniones), "multiArticleBefore": sum(1 for c in clusters if c["size"] > 1),
                   "multiArticleAfter": len(multi),
                   "independent2PlusBefore": sum(1 for c in clusters if c.get("independentProvenanceCount", 0) >= 2),
                   "independent2PlusAfter": sum(1 for c in salida if c.get("independentProvenanceCount", 0) >= 2)},
        "sampleLinks": [{"a": by_id[u["a"]]["title"], "b": by_id[u["b"]]["title"], "score": u["score"]}
                        for u in sorted(uniones, key=lambda u: u["score"])[:25]],
        "limits": "Solo titulares; el umbral se ajustó revisando uniones de borde y debe validarse con pares etiquetados por personas.",
    }
    (out / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(meta["counts"], ensure_ascii=False))


if __name__ == "__main__":
    main()
