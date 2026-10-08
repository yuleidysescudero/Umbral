"""Preguntas literales del jurado y correcciones de la revisión final (8 oct): pruebas escritas antes de cada arreglo."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from umbral_api.app import create_app
from umbral_api.services import Services

from .conftest import make_settings

REAL = Path(__file__).resolve().parents[3] / "data" / "snapshots" / "20261007-cfa338b6"
pytestmark = pytest.mark.skipif(not REAL.exists(), reason="snapshot real no disponible")

Q_INFLACION = "Muéstrame de dónde proviene la cifra de inflación de Panamá y de qué año es"
Q_AGENCIA = "Si cinco medios replican la misma agencia, ¿cuántas fuentes independientes cuentas?"


@pytest.fixture(scope="module")
def real(tmp_path_factory):
    os.environ["UMBRAL_SEMANTIC_CLUSTERS"] = "1"
    settings = make_settings(REAL, tmp_path_factory.mktemp("jurado"))
    svc = Services(settings)
    client = TestClient(create_app(settings, services=svc), headers={"X-Umbral-User": "jurado"})
    client.svc = svc  # type: ignore[attr-defined]
    return client


def ask(client, q, **kw):
    r = client.post("/api/v1/queries", json={"question": q, **kw})
    assert r.status_code == 200, r.text
    return r.json()


# ---------------------------------------------------------------- 1a. de dónde proviene la cifra
def test_inflacion_proviene_no_es_un_pais(real):
    r = ask(real, Q_INFLACION)
    assert r["intent"] == "contexto_economico"
    assert r["answerStatus"] == "respondida", r["answer"]
    a = r["answer"]
    assert "Inflación" in a and "Panamá" in a
    assert "2024" in a  # último año con dato en el paquete
    assert "%" in a  # unidad
    assert "Banco Mundial" in a
    assert "https://api.worldbank.org/v2/country/PAN/indicator/FP.CPI.TOTL.ZG" in a  # URL visible, no solo en la cita
    assert "dato anual, no de hoy" in a
    assert "proviene" not in a.lower().split("«")[0]  # no se reporta como entidad desconocida
    ids = {c["evidenceId"] for c in r["citations"]}
    assert ids == {"ind_PAN_FP.CPI.TOTL.ZG_2024"}


@pytest.mark.parametrize("q", [
    "¿De dónde sale el dato de desempleo de Panamá?",
    "Enséñame el origen de la cifra del PIB de Costa Rica",
    "Explícame de dónde viene la población de Panamá",
])
def test_verbos_de_peticion_no_son_entidades(real, q):
    r = ask(real, q)
    assert r["intent"] == "contexto_economico"
    assert r["answerStatus"] != "abstencion", r["answer"]


def test_entidad_desconocida_sigue_abstenida(real):
    r = ask(real, "inflación de Marte en 2023")
    assert r["answerStatus"] == "abstencion"
    assert "marte" in r["answer"].lower()


# ---------------------------------------------------------------- 1b. regla de procedencia
def test_regla_procedencia_con_ejemplo_real(real):
    r = ask(real, Q_AGENCIA)
    assert r["intent"] == "regla_procedencia"
    assert r["answerStatus"] == "respondida", r["answer"]
    a = r["answer"]
    assert "una" in a.lower() and "procedencia" in a.lower()
    assert "cuenta como una sola procedencia" in a.lower() or "cuentan como una sola procedencia" in a.lower()
    # Ejemplo real del snapshot: el tema del Canal con 8 notas y 7 procedencias (dos notas de Xinhua = una).
    assert "8 notas" in a and "7 procedencias" in a
    assert "xinhua" in a.lower()
    cited = {c["evidenceId"] for c in r["citations"]}
    assert {"art_86082bb0c12b33ce", "art_b5c6a54bb796fd6e"} <= cited
    assert all(cid.startswith("art_") for cid in cited)
    assert r["relatedTopicIds"] == ["evt_d1e3e4027d55dc34"]


def test_pregunta_ambigua_de_fuente_independiente_no_cambia(real):
    # dev_22 del benchmark: no es la regla, es una pregunta sobre TVN; no debe secuestrarla la nueva intención.
    r = ask(real, "¿Qué fuente independiente confirma todos los titulares de TVN?")
    assert r["intent"] != "regla_procedencia"


def test_casos_del_jurado_en_el_benchmark():
    import json

    path = Path(__file__).resolve().parents[3] / "eval" / "dev" / "benchmark_dev.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    by_q = {r["question"]: r for r in rows}
    for q in (Q_INFLACION, Q_AGENCIA):
        assert q in by_q, q
        assert by_q[q]["mustAbstain"] is False
        assert by_q[q]["relevantEvidenceIds"]


# ---------------------------------------------------------------- 2. citas sin relación
def test_reforma_electrica_no_cita_reformas_electorales(real):
    r = ask(real, "¿Qué pasó con la reforma eléctrica?")
    assert r["answerStatus"] != "abstencion", r["answer"]
    passages = [c["passage"].lower() for c in r["citations"]] + [c["title"].lower() for c in r["citations"]]
    assert passages
    assert not any("electoral" in p for p in passages), passages
    assert "electoral" not in r["answer"].lower()
    assert any("eléctrica" in p for p in passages)


def test_cita_exige_las_palabras_de_contenido(real):
    # Cada artículo citado en una búsqueda comparte las palabras de contenido de la consulta (sin stemming difuso).
    from umbral_api.retrieval import tokenize

    for q in ("¿Qué pasó con la reforma eléctrica?", "tránsitos del Canal de Panamá"):
        r = ask(real, q)
        engine = real.svc.engine
        content = engine._content_terms(q)
        need = -(-2 * len(content) // 3)
        for c in r["citations"]:
            if not c["evidenceId"].startswith("art_"):
                continue
            art = real.svc.corpus.articles[c["evidenceId"]]
            if "semantico" in r["retrieval"]["method"] and art.language == "en":
                continue  # traducción traída por los vecinos semánticos de un resultado léxico fuerte
            title = art.title
            assert len(set(tokenize(title)) & content) >= need, (q, title, content)


# ---------------------------------------------------------------- 3. guion del borrador
def _templates(real):
    from umbral_api.drafts import build_template_package

    for b in real.svc.bases.values():
        if not b.usable_articles:
            continue
        yield b, build_template_package(b, score=60.0, band="media", status=b.system_status.value)


def test_guion_no_afirma_que_tvn_consulta(real):
    from umbral_api.drafts import SCRIPT_NOTES_LABEL, spoken_part

    for b, pkg in _templates(real):
        assert "El equipo de TVN consulta" not in pkg.script, b.id
        notes = pkg.script.split(SCRIPT_NOTES_LABEL)[1]
        assert "Pendiente: solicitar confirmación a" in notes, b.id
        assert "consulta a" not in spoken_part(pkg.script), b.id


def test_guion_sin_a_el(real):
    import re

    for b, pkg in _templates(real):
        assert not re.search(r"\b[aA] el\b", pkg.script), (b.id, pkg.script)
        assert not re.search(r"\b[dD]e el\b", pkg.script), (b.id, pkg.script)


def test_guion_no_lee_titulares_en_ingles(real):
    from umbral_api.drafts import SCRIPT_NOTES_LABEL, spoken_part

    b = real.svc.bases["evt_d1e3e4027d55dc34"]  # Canal: representante en inglés (newsroompanama.com)
    assert b.representative.language == "en"
    from umbral_api.drafts import build_template_package

    pkg = build_template_package(b, score=76.7, band="alto", status=b.system_status.value)
    spoken = spoken_part(pkg.script)
    assert b.representative.title.rstrip(" .") not in spoken
    assert "Increases Daily Transits" not in spoken
    assert "un medio internacional" in spoken.lower()
    assert "[c" in spoken  # la afirmación sigue citada
    notes = pkg.script.split(SCRIPT_NOTES_LABEL)[1]
    assert "Panama Canal Increases Daily Transits to 33" in notes  # el original queda en las notas


def test_guion_sin_versiones_distintas_con_una_sola_fuente(real):
    from umbral_api.drafts import spoken_part

    singles = 0
    for b, pkg in _templates(real):
        if b.independent < 2:
            singles += 1
            assert "versiones distintas" not in spoken_part(pkg.script), b.id
    assert singles > 10


def test_guion_sigue_en_rango_y_valido(real):
    from umbral_api.drafts import build_pack, validate_package

    bad = []
    for b, pkg in _templates(real):
        _, report = validate_package(pkg, build_pack(b))
        if any(i.code == "guion_fuera_de_rango" for i in report.issues):
            bad.append(b.id)
    assert not bad, bad[:5]


# ---------------------------------------------------------------- 4. empates del ranking (scoring-v2)
@pytest.fixture(scope="module")
def v2(tmp_path_factory):
    old = os.environ.get("UMBRAL_SCORING")
    os.environ["UMBRAL_SCORING"] = "v2"
    os.environ["UMBRAL_SEMANTIC_CLUSTERS"] = "1"
    settings = make_settings(REAL, tmp_path_factory.mktemp("v2"))
    svc = Services(settings)
    client = TestClient(create_app(settings, services=svc), headers={"X-Umbral-User": "jurado"})
    client.svc = svc  # type: ignore[attr-defined]
    yield client
    if old is None:
        os.environ.pop("UMBRAL_SCORING", None)
    else:
        os.environ["UMBRAL_SCORING"] = old


def test_agenda_por_defecto_sin_empates_masivos(v2):
    import collections

    for params in ({"limit": 100}, {"limit": 100, "scope": "all"}):
        items = v2.get("/api/v1/topics", params=params).json()["items"]
        assert len(items) == 100
        # Mismo criterio que test_qa_tvn._ties: el puntaje exacto (54,55 era el empate de 51 temas en la agenda por defecto).
        worst = collections.Counter(t["score"] for t in items).most_common(1)[0]
        assert worst[1] <= 10, (params, worst)
        # Con un decimal en pantalla, los temas detectados en la misma tanda de horas siguen juntos; se acota igual.
        shown = collections.Counter(t["scoreDisplay"] for t in items).most_common(1)[0]
        assert shown[1] <= 15, (params, shown)


def test_u_usa_deteccion_y_lo_dice(v2):
    items = v2.get("/api/v1/topics", params={"limit": 100}).json()["items"]
    sin_fecha = [t for t in items if not t["firstPublishedAt"]]
    assert sin_fecha
    for t in sin_fecha[:10]:
        u = next(c for c in t["scoreComponents"] if c["key"] == "U")
        assert u["value"] > 0, t["id"]
        assert "detección" in u["justification"], u["justification"]


# ---------------------------------------------------------------- 5. asistente
@pytest.mark.parametrize("q", ["Qué temas no ha cubierto TVN", "¿Qué temas no ha publicado TVN?", "temas sin cobertura de TVN"])
def test_temas_no_cubiertos_por_tvn_filtra_tvn_gap(real, q):
    r = ask(real, q)
    assert r["intent"] == "agenda", r["intent"]
    assert r["answerStatus"] == "respondida", r["answer"]
    gaps = {t["id"] for t in real.get("/api/v1/topics", params={"limit": 100, "tvnGap": True}).json()["items"]}
    assert r["relatedTopicIds"] and set(r["relatedTopicIds"]) <= gaps
    for tid in r["relatedTopicIds"]:
        base = real.svc.bases[tid]
        assert not any(a.is_tvn for a in base.articles), tid
    assert "TVN" in r["answer"] and "no" in r["answer"]


def test_temas_relacionados_traen_titulo(real):
    r = ask(real, "¿Qué pasó con la reforma eléctrica?")
    assert r["relatedTopics"], r
    assert [t["id"] for t in r["relatedTopics"]] == r["relatedTopicIds"]
    for t in r["relatedTopics"]:
        assert t["title"] and not t["title"].startswith("evt_")
        assert t["title"] == real.svc.bases[t["id"]].display_title


# ---------------------------------------------------------------- 7. deportes fuera de alcance
DEPORTES = ("Panamá cae en penales ante Nueva Zelanda", "Japón elimina a la Ecuador de Gallardo")


def _titles(items):
    return [t["title"] for t in items]


def test_deportes_fuera_de_la_agenda(real):
    def agenda(**kw):
        return real.svc.list_topics("jurado", limit=1000, category=None, evidence=None, band=None, review_status=None,
                                    q=None, include_components=False, **kw).items

    items = agenda()
    for name in DEPORTES:
        assert not any(name in t.title for t in items), name
    for name in DEPORTES:
        t = next(t for t in agenda(scope="all") if name in t.title)
        assert t.out_of_scope is True, t.title  # sigue visible en «todos», marcado fuera de alcance
    top = real.get("/api/v1/topics", params={"limit": 100}).json()["items"]
    assert not any(n in t["title"] for t in top for n in DEPORTES)


@pytest.mark.parametrize("q", ["resumen de economía de esta semana", "Qué cinco temas merecen revisión para la agenda de Panamá",
                               "Qué temas no ha cubierto TVN"])
def test_deportes_fuera_de_resumenes_y_agenda_del_asistente(real, q):
    r = ask(real, q)
    for name in DEPORTES:
        assert name not in r["answer"], (q, name)


@pytest.mark.parametrize("title,sport", [
    ("Panamá cae en penales ante Nueva Zelanda en las semifinales de la Copa Kirin", True),
    ("0 - 0 ( 5 - 4 ): Japón elimina a la Ecuador de Gallardo", True),
    ("El DT de la selección convoca a 23 jugadores para la eliminatoria", True),
    ("Gol de último minuto en el partido ante Costa Rica por la Liga", True),
    ("Registro de Buques de Panamá cae al tercer lugar mundial por tonelaje de arqueo bruto", False),
    ("España llega a la recta final antes del invierno con menos gas almacenado", False),
    ("Banco Mundial mejora la proyección de crecimiento de Panamá", False),
    ("Copa Airlines anuncia nueva ruta a Lima", False),
    ("El partido Realizando Metas presenta su candidato", False),
    ("Proceso de selección de personal en la ACP", False),
])
def test_detector_de_titulares_deportivos(title, sport):
    from umbral_api.topics import is_sports_title

    assert is_sports_title(title) is sport
