"""Agrupación semántica precalculada: se usa solo si los hashes cuadran; si no, se sirven los grupos del snapshot."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from umbral_api.snapshot import load_corpus

from .conftest import make_settings


def _semantic_copy(fixture_dir: Path, tmp_path: Path, *, tamper: bool = False) -> Path:
    snap = tmp_path / "snapshots" / fixture_dir.name
    shutil.copytree(fixture_dir, snap)
    manifest = json.loads((snap / "manifest.json").read_text(encoding="utf-8"))
    rows = [json.loads(line) for line in (snap / "clusters.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    a, b = rows[0], rows[1]
    merged = {**a, "clusterId": "evt_semantico_prueba", "memberArticleIds": a["memberArticleIds"] + b["memberArticleIds"],
              "size": a["size"] + b["size"], "mergedFromClusterIds": [a["clusterId"], b["clusterId"]]}
    out = [merged] + rows[2:]
    text = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in out)
    folder = tmp_path / "agrupacion" / str(manifest.get("snapshotId") or snap.name)
    folder.mkdir(parents=True)
    (folder / "clusters.semantic.jsonl").write_bytes((text + ("{}\n" if tamper else "")).encode("utf-8"))
    meta = {"clustersSha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "sourceClustersSha256": hashlib.sha256((snap / "clusters.jsonl").read_bytes()).hexdigest()}
    (folder / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    return snap


def test_semantic_clusters_are_used_when_enabled_and_hashes_match(fixture_dir, tmp_path, monkeypatch):
    snap = _semantic_copy(fixture_dir, tmp_path)
    monkeypatch.setenv("UMBRAL_SEMANTIC_CLUSTERS", "1")
    corpus = load_corpus(make_settings(snap))
    assert "evt_semantico_prueba" in corpus.clusters


def test_semantic_clusters_are_ignored_when_disabled(fixture_dir, tmp_path, monkeypatch):
    snap = _semantic_copy(fixture_dir, tmp_path)
    monkeypatch.delenv("UMBRAL_SEMANTIC_CLUSTERS", raising=False)
    assert "evt_semantico_prueba" not in load_corpus(make_settings(snap)).clusters


def test_tampered_semantic_clusters_are_ignored(fixture_dir, tmp_path, monkeypatch):
    snap = _semantic_copy(fixture_dir, tmp_path, tamper=True)
    monkeypatch.setenv("UMBRAL_SEMANTIC_CLUSTERS", "1")
    assert "evt_semantico_prueba" not in load_corpus(make_settings(snap)).clusters
