"""Consultas en español con evidencia: recuperación BM25+RapidFuzz, citas y abstención explícita."""

from __future__ import annotations

import re
import time
import uuid
from datetime import timedelta

from .cifras import exact_str, fmt_es, format_value_es, score_display
from .models import (
    CATEGORY_LABELS,
    AnswerStatus,
    Contradiction,
    DataMode,
    IndicatorPoint,
    QueryCitation,
    QueryHit,
    QueryIntent,
    QueryRequest,
    QueryResponse,
    RetrievalInfo,
    TopicSummary,
)
from .retrieval import Doc, Hit, SearchIndex, fold, tokenize
from .scoring import RULES_VERSION, base_rules_version
from .security import looks_like_instruction, looks_like_profiling, split_injection
from .snapshot import Corpus, parse_dt
from .topics import COUNTRY_KEYWORDS, INDICATOR_KEYWORDS, MASKED_TITLE, TopicBase, cross_contradictions
from .util import fmt_date_pa

INDICATOR_ES = {
    "NY.GDP.MKTP.KD.ZG": "crecimiento del PIB producto interno bruto crecimiento económico",
    "FP.CPI.TOTL.ZG": "inflación precios al consumidor costo de vida",
    "SL.UEM.TOTL.ZS": "desempleo tasa de desempleo mercado laboral",
    "SP.POP.TOTL": "población habitantes demografía",
    "IT.NET.USER.ZS": "uso de internet usuarios de internet conectividad",
    "NE.EXP.GNFS.ZS": "exportaciones de bienes y servicios comercio exterior porcentaje del PIB",
}
INDICATOR_LABEL_ES = {
    "NY.GDP.MKTP.KD.ZG": "Crecimiento del PIB",
    "FP.CPI.TOTL.ZG": "Inflación (precios al consumidor)",
    "SL.UEM.TOTL.ZS": "Desempleo",
    "SP.POP.TOTL": "Población total",
    "IT.NET.USER.ZS": "Uso de internet",
    "NE.EXP.GNFS.ZS": "Exportaciones de bienes y servicios",
}
_COUNTRY_ES = {"PAN": "Panamá", "CRI": "Costa Rica", "COL": "Colombia", "DOM": "República Dominicana", "MEX": "México", "GTM": "Guatemala"}

_GENERIC_ECON = {
    "econom", "economico", "contexto", "indicador", "indicadores", "banco", "mundial", "oficial", "oficiales", "dato",
    "datos", "valor", "valores", "ano", "anos", "serie", "ultimo", "ultima", "actual", "actuales", "cifra", "cifras",
    "nivel", "tasa", "porcentaje", "anual", "pais", "paises", "comparado", "compara", "comparar", "evolucion",
    "tendencia", "periodo", "unidad", "fuente", "tema", "dame", "dime", "muestra", "pib", "inflacion", "desempleo",
    "poblacion", "internet", "exportacion", "exportaciones", "crecimiento", "cuant", "cual", "como",
}
_RE_AGENDA = re.compile(r"\b(cinco|5|principales)\b.*\btemas?\b|\bque temas?\b|\bagenda\b|merecen revision|\bpriorid\w*|\bprioriz\w*")
_RE_VERIF = re.compile(r"falta(n)?\s+(por\s+)?verificar|verificaciones?|pendientes?\s+de\s+verif|que falta|vacios|por comprobar|falta comprobar")
_RE_ECON = re.compile(r"contexto economico|indicadores?|banco mundial|\bpib\b|inflacion|desempleo|poblacion|\binternet\b|exportacion|crecimiento economico")
_RE_NUMERIC = re.compile(r"\bcuant[oa]s?\b|\bcifra\b|\bmonto\b|\bporcentaje\b|\bnumero de\b|\btotal de\b|\bcuanto cuesta\b")
_RE_YEAR = re.compile(r"\b((?:19|20)\d{2})\b")
_RE_TODAY = re.compile(r"\bhoy\b|\bactual(es|mente)?\b|\beste (ano|mes)\b|\bahora\b|\besta semana\b")
# Palabras de la consulta que no nombran tema, país ni indicador («según», «fue»…): no son entidades desconocidas.
_QUERY_WORDS = {
    "segun", "fue", "era", "es", "son", "registro", "registra", "reporta", "reporto", "dice", "dijo", "indica",
    "tuvo", "tiene", "hubo", "hay", "cuanto", "cuanta", "cuantos", "cuantas", "sabe", "saber", "informa",
    # Peticiones y verbos de procedencia («muéstrame de dónde proviene…»): forma de la pregunta, no un país.
    "muestrame", "mostrar", "ensename", "ensenar", "explica", "explicame", "indicame", "quiero", "ver", "donde",
    "proviene", "provienen", "viene", "vienen", "sale", "salen", "sacan", "origen", "procede", "proceden",
    "procedencia", "obtiene", "obtuvo",
}
_NUMBER_WORDS = {"dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10}
# «Si cinco medios replican la misma agencia, ¿cuántas fuentes independientes cuentas?»: pregunta por la regla.
_REPLICA = r"(replic|repit|reproduc|copi|retom|republic)\w*"
_RE_PROVENANCE_RULE = re.compile(
    rf"\bagencias?\b.*\b{_REPLICA}|\b{_REPLICA}.*\bagencias?\b"
    r"|\bcuant[oa]s\s+(fuentes|procedencias)\s+independientes\b|\bregla de procedencia\b"
)

_MONEY = r"(\$|us\$|b/\.|usd)\s*\d|\d[\d.,]*\s*(millones|mil millones|dolares|balboas)"
# Tipo de cifra pedida → (etiqueta, patrón en la pregunta, patrón que debe tener UN titular pertinente, qué falta).
# «¿Cuántos murieron por el sismo?» no se responde con «Sismo de magnitud 5,4»: tener un número no basta.
_NUMBER_KINDS = [
    ("pérdidas económicas",
     re.compile(r"perd(io|ieron|ida|idas|ido)\b|\bperdidas?\b|danos economicos|impacto economico"),
     re.compile(r"(perdida|perdio|perdieron|danos|impacto|afectacion).{0,80}(" + _MONEY + r")|(" + _MONEY
                + r").{0,80}(perdida|danos|impacto)"),
     "Una estimación oficial de pérdidas con monto, moneda y periodo."),
    ("una cifra de personas",
     re.compile(r"cuant[oa]s\s+(personas|muertos|fallecidos|murieron|heridos|evacuados|afectados|victimas|turistas|"
                r"visitantes|trabajadores|empleos|familias)|cuant[oa]s\s+\w+\s+(murieron|fallecieron|resultaron)"),
     re.compile(r"\d[\d.,]*\s*(personas|muert|fallec|herid|evacuad|afectad|victimas|turistas|visitantes|trabajador|"
                r"empleos|familias)"),
     "El conteo oficial con fecha de corte y la institución que lo publica (SINAPROC, MINSA u otra)."),
    ("un monto en dinero",
     re.compile(r"\bdinero\b|\bmonto\b|cuanto (cuesta|costo|recaud|invirt|pag)|\bdolares\b|\bbalboas\b"),
     re.compile(_MONEY),
     "El monto oficial con moneda, periodo y fuente."),
    ("un porcentaje",
     re.compile(r"\bporcentaje\b|por ciento|%"),
     re.compile(r"\d[\d.,]*\s*(%|por ciento)"),
     "El indicador con su unidad (%), el periodo y la fuente oficial."),
]


_RE_ASKS_QUANTITY = re.compile(r"\bcuant[oa]s?\b|\bcifra\b|\bmonto\b|\bporcentaje\b|\bnumero de\b|\btotal de\b|por ciento")
# Para conteos de personas, la cifra del titular debe ser del MISMO tipo: «3 heridos» no responde «¿cuántos murieron?».
_PERSON_FAMILIES = [
    (r"muert|murier|fallec|victimas mortales", r"muert|fallec|decesos?|vidas"),
    (r"herid", r"herid|lesionad"),
    (r"evacu", r"evacu"),
    (r"afectad|damnificad", r"afectad|damnificad"),
    (r"turist|visitant", r"turist|visitant|pasajer"),
    (r"emple|trabajador", r"emple|trabajador|puestos"),
    (r"familias", r"familias"),
]


def _number_kind(folded_question: str) -> tuple[str, re.Pattern[str], re.Pattern[str], str] | None:
    if not _RE_ASKS_QUANTITY.search(folded_question):
        return None  # mencionar «dinero» o «pérdidas» no es pedir una cifra
    kind = next((k for k in _NUMBER_KINDS if k[1].search(folded_question)), None)
    if kind is not None and kind[0] == "una cifra de personas":
        nouns = [ev for asked, ev in _PERSON_FAMILIES if re.search(asked, folded_question)]
        if nouns:
            evidence = re.compile(r"\d[\d.,]*\s*(\w+\s+){0,2}(" + "|".join(nouns) + ")")
            return (kind[0], kind[1], evidence, kind[3])
    return kind


_RE_SEISMIC = re.compile(r"\bsism\w*|\btemblor\w*|\bterremoto\w*|\bmagnitud\w*|\bepicentro\w*|\bearthquake")
# Daños humanos o materiales: USGS no es evidencia de eso; esas preguntas siguen el camino de titulares/abstención.
_RE_HUMAN_IMPACT = re.compile(r"muert|murier|fallec|herid|victim|evacu|afectad|damnific|dano|danos|perdid|destru|inund")
INJECTION_WARNING = "inyeccion_detectada"
SEISMIC_BOX_NOTE = "La caja regional (lat 5–12, lon −86 a −76) no equivale al territorio de Panamá."
SEISMIC_DAMAGE_NOTE = "USGS no es evidencia de daños, inundaciones ni pérdidas."


_RE_GUILT = re.compile(r"\bes (verdad|cierto|falso) que\b|\bculpables?\b|\binocentes?\b")
_RE_GUILT_STRIP = re.compile(r"(?i)\bes (verdad|cierto|falso) que\b|\b(es|son|fue|fueron)\s+(culpables?|inocentes?)\b|\bculpables?\b|\binocentes?\b")
# Listas de personas («quiénes son los culpables», «lista de sospechosos») siguen siendo perfilamiento: se rechazan.
_RE_LIST_PROFILING = re.compile(r"\blista\b|\bquienes\b|\bque (personas|politicos|funcionarios)\b|\bcuales\b")
_RE_SUMMARY = re.compile(
    r"\bresum\w*|\bpanorama\b|\bnovedades\b|\blo mas (importante|destacado)\b|\bprincipales (noticias|temas)\b"
)
# «¿Qué pasó con la reforma eléctrica?» es una búsqueda; solo con un periodo («qué pasó esta semana en turismo») es resumen.
_RE_SUMMARY_WITH_PERIOD = re.compile(r"\bque (ha )?paso\b|\bque hay de\b|\bcuentame\b|\bmuestrame\b")
_CATEGORY_WORDS: list[tuple[str, str]] = [
    (r"\becono\w*|\bfinanz\w*|\bempleo\b|\bprecios\b", "economia"),
    (r"\bcanal\b|\blogistic\w*|\bpuertos?\b|\btransitos?\b|\bnaviera\w*", "logistica_canal"),
    (r"\bturis\w*|\bvisitantes\b|\bhotel\w*", "turismo"),
    (r"\bservicios publicos\b|\bagua\b|\belectric\w*|\benergia\b|\bluz\b|\btransporte\b|\bbasura\b", "servicios_publicos"),
    (r"\beventos naturales\b|\blluvias?\b|\bclima\b|\binundaci\w*|\bsism\w*|\bincendio\w*", "eventos_naturales"),
    (r"\bregula\w*|\bleyes\b|\bley\b|\bnormativ\w*|\breforma\w*|\bdecreto\w*", "regulacion"),
]


def _period(f: str) -> tuple[str, timedelta, timedelta] | None:
    """Expresión temporal → (texto, desde, hasta) relativos al corte del snapshot."""
    if re.search(r"\bhoy\b", f):
        return "hoy (24 h previas al corte)", timedelta(hours=24), timedelta(0)
    if re.search(r"\bayer\b", f):
        return "ayer (entre 24 y 48 h antes del corte)", timedelta(hours=48), timedelta(hours=24)
    m = re.search(r"\bultim[oa]s?\s+(\d{1,2})\s+dias\b", f)
    if m:
        n = int(m.group(1))
        return f"los últimos {n} días antes del corte", timedelta(days=n), timedelta(0)
    if re.search(r"\besta semana\b|\bla semana\b|\bsemanal\b|\bultima semana\b", f):
        return "los 7 días previos al corte", timedelta(days=7), timedelta(0)
    if re.search(r"\beste mes\b|\bultimo mes\b|\bel mes\b", f):
        return "los 30 días previos al corte", timedelta(days=30), timedelta(0)
    return None


def _category(f: str) -> str | None:
    return next((cat for pat, cat in _CATEGORY_WORDS if re.search(pat, f)), None)


def _detect_intent(q: str) -> QueryIntent:
    f = fold(q)
    if _RE_PROVENANCE_RULE.search(f):
        return QueryIntent.regla_procedencia
    summary = (_RE_SUMMARY.search(f) and (_category(f) or _period(f))) or (_RE_SUMMARY_WITH_PERIOD.search(f) and _period(f))
    if summary and not _RE_ASKS_QUANTITY.search(f):
        return QueryIntent.resumen_periodo
    if _RE_VERIF.search(f):
        return QueryIntent.verificaciones
    if _RE_SEISMIC.search(f) and not _RE_HUMAN_IMPACT.search(f):
        return QueryIntent.eventos_sismicos
    if _RE_AGENDA.search(f):
        return QueryIntent.agenda
    if _RE_ECON.search(f):
        return QueryIntent.contexto_economico
    return QueryIntent.busqueda


class QueryEngine:
    def __init__(self, corpus: Corpus, bases: dict[str, TopicBase]):
        self.corpus = corpus
        self.bases = bases
        docs: list[Doc] = []
        for a in corpus.articles.values():
            docs.append(Doc(a.id, "articulo", f"{a.title} {a.outlet}", a.cluster_id))
        for p in corpus.indicators.values():
            docs.append(
                Doc(
                    p.id,
                    "indicador",
                    f"{INDICATOR_ES.get(p.indicator_id, p.indicator_name)} {p.country_name or ''} {p.country_iso3} {p.year} indicador oficial",
                )
            )
        self.index = SearchIndex(docs)
        self._doc_by_id = {d.doc_id: d for d in docs}
        self.article_ids = set(corpus.articles)

    # ------------------------------------------------------------------ API
    def answer(self, req: QueryRequest, agenda: list[TopicSummary]) -> QueryResponse:
        t0 = time.perf_counter()
        q = req.question.strip()
        warnings: list[str] = []
        if looks_like_instruction(q):
            warnings.append(
                "La consulta contiene texto con forma de instrucción; se trata solo como texto de búsqueda y no cambia el comportamiento del sistema."
            )
        intent = _detect_intent(q)
        if warnings:
            warnings.insert(0, INJECTION_WARNING)
            legit, _fragment = split_injection(q)
            if len(tokenize(legit)) >= 2 and not looks_like_instruction(legit):
                # Se rechaza el fragmento y se responde SOLO la parte legítima (el fragmento no se repite).
                inner = self.answer(req.model_copy(update={"question": legit}), agenda)
                inner.question = req.question
                inner.answer = (
                    "Rechacé un fragmento de tu mensaje porque intenta darle órdenes al sistema (marcas de rol, "
                    "delimitadores o acciones como aprobar o publicar). No se ejecutó nada.\n\n"
                    f"Sobre «{legit}»: " + inner.answer
                )
                inner.warnings = warnings + inner.warnings
                return inner
            # T07: la instrucción no se ejecuta ni se busca; se rechaza de forma explícita y auditable.
            return self._abstain(
                req, intent, t0,
                "la consulta intenta cambiar las reglas del sistema o revelar su configuración. "
                "Ese texto se trata como dato y no se ejecuta; solo respondo con evidencia del corpus.",
                warnings, missing=["Una pregunta sobre un tema del corpus."],
            )
        guilt = _RE_GUILT.search(fold(q))
        if guilt and not _RE_LIST_PROFILING.search(fold(q)):
            # «¿Es verdad que X es culpable?»: se busca el hecho publicado y se presenta como atribución, nunca como veredicto.
            topic_q = _RE_GUILT_STRIP.sub(" ", q).strip(" ¿?")
            guilt_resp = self._busqueda(req.model_copy(update={"question": topic_q}), None, t0) if len(tokenize(topic_q)) >= 1 else None
            first = next((c for c in (guilt_resp.citations if guilt_resp else []) if c.evidence_id in self.corpus.articles), None)
            source = self.corpus.articles[first.evidence_id].outlet if first else "la fuente que lo publique"
            notice = (
                "Umbral no determina culpabilidad ni verdad. Lo publicado es una atribución: «señalado por…» "
                f"según {source}. La responsabilidad penal solo la determina un tribunal."
            )
            if guilt_resp is None or guilt_resp.answer_status == AnswerStatus.abstencion:
                return self._abstain(req, intent, t0, notice + " Además, no hay en el corpus una nota que respalde el hecho consultado.",
                                     ["Pregunta de culpabilidad: se responde solo con atribuciones publicadas."])
            guilt_resp.question = req.question
            guilt_resp.answer = notice + "\n\n" + guilt_resp.answer
            guilt_resp.warnings = ["Pregunta de culpabilidad: se muestran atribuciones publicadas, no un veredicto."] + guilt_resp.warnings
            return guilt_resp
        if looks_like_profiling(q):
            return self._abstain(
                req, intent, t0,
                "no señalo personas como sospechosas o culpables ni armo listas de supuestos delincuentes "
                "(privacidad y reputación). Puedo mostrar qué acusaciones se publicaron, atribuidas a quien las hizo.",
                ["Consulta de perfilamiento de personas: rechazada por política de privacidad."],
                missing=["Una pregunta sobre un hecho o tema, no sobre la culpabilidad de personas."],
            )
        scope = None
        if req.topic_id:
            scope = self.bases.get(req.topic_id)
            if scope is None:
                return self._abstain(req, intent, t0, "El tema indicado no existe en el snapshot servido.", warnings)

        if intent == QueryIntent.eventos_sismicos and not self.corpus.events:
            intent = QueryIntent.busqueda  # paquete sin events.geojson (fixture): se buscan titulares
        if intent == QueryIntent.regla_procedencia:
            resp = self._regla_procedencia(req, scope, t0)
        elif intent == QueryIntent.resumen_periodo:
            resp = self._resumen(req, agenda, t0)
        elif intent == QueryIntent.eventos_sismicos:
            resp = self._sismos(req, t0)
        elif intent == QueryIntent.agenda:
            resp = self._agenda(req, agenda, t0)
        elif intent == QueryIntent.verificaciones:
            resp = self._verificaciones(req, scope, t0)
        elif intent == QueryIntent.contexto_economico:
            resp = self._economico(req, scope, t0)
        else:
            resp = self._busqueda(req, scope, t0)
        resp.warnings = warnings + resp.warnings
        return resp

    # ------------------------------------------------------------------ helpers
    def _base_resp(self, req: QueryRequest, intent: QueryIntent, t0: float, **kw) -> QueryResponse:  # noqa: ANN003
        return QueryResponse(
            query_id="q_" + uuid.uuid4().hex[:12],
            question=req.question,
            intent=intent,
            answer_status=kw.pop("answer_status"),
            answer=kw.pop("answer"),
            snapshot_id=self.corpus.snapshot_id,
            rules_version=RULES_VERSION,
            data_mode=self.corpus.data_mode,
            retrieval=RetrievalInfo(
                method=kw.pop("method", "bm25+rapidfuzz"),
                corpus_size=len(self.index.docs),
                took_ms=round((time.perf_counter() - t0) * 1000, 2),
                matched_terms=kw.pop("matched_terms", []),
                coverage=kw.pop("coverage", 0.0),
            ),
            **kw,
        )

    def _abstain(self, req: QueryRequest, intent: QueryIntent, t0: float, reason: str, warnings: list[str] | None = None,
                 missing: list[str] | None = None, hits: list[QueryHit] | None = None, coverage: float = 0.0,
                 matched: list[str] | None = None) -> QueryResponse:
        return self._base_resp(
            req,
            intent,
            t0,
            answer_status=AnswerStatus.abstencion,
            answer=(
                "No puedo responder con la evidencia del corpus: " + reason +
                " No se inventan cifras, declaraciones ni fuentes."
            ),
            abstention_reason=reason,
            missing=missing or ["Una fuente en el corpus que respalde la consulta."],
            hits=hits or [],
            warnings=warnings or [],
            coverage=coverage,
            matched_terms=matched or [],
        )

    def _hit_model(self, h, art_only: bool = True) -> QueryHit:  # noqa: ANN001
        d = h.doc
        if d.kind == "articulo":
            a = self.corpus.articles[d.doc_id]
            shown = MASKED_TITLE if a.suspicious_instructions else a.title  # nunca se reproduce texto con instrucciones
            return QueryHit(
                evidence_id=a.id, kind="articulo", title=shown, url=a.url, outlet=a.outlet, published_at=a.published_at,
                snippet=shown, bm25=round(h.bm25, 4), fuzzy=round(h.fuzzy, 4), relevance=h.relevance,
                cluster_id=a.cluster_id, suspicious_instructions=a.suspicious_instructions,
            )
        p = self.corpus.indicators[d.doc_id]
        return QueryHit(
            evidence_id=p.id, kind="indicador", title=f"{p.indicator_name} · {p.country_iso3} · {p.year}", url=p.source_url,
            outlet="Banco Mundial", snippet=_ind_text(p), bm25=round(h.bm25, 4), fuzzy=round(h.fuzzy, 4),
            relevance=h.relevance,
        )

    def _when(self, hit):  # noqa: ANN001, ANN202
        a = self.corpus.articles[hit.doc.doc_id]
        return a.published_at or a.detected_at

    def _unknown_entities(self, question: str, scope: TopicBase | None) -> list[str]:
        """Términos de la pregunta que no son indicador, país, año ni palabra genérica (p. ej. «Marte»)."""
        known: set[str] = set(_GENERIC_ECON) | _QUERY_WORDS
        for w in _GENERIC_ECON | _QUERY_WORDS:
            known.update(tokenize(w))
        for kws in list(INDICATOR_KEYWORDS.values()) + list(COUNTRY_KEYWORDS.values()):
            for kw in kws:
                known.update(tokenize(kw))
        for iso, name in _COUNTRY_ES.items():
            known.update(tokenize(name))
            known.add(fold(iso))
        for txt in list(INDICATOR_ES.values()) + list(INDICATOR_LABEL_ES.values()):
            known.update(tokenize(txt))
        if scope is not None:
            known.update(tokenize(scope.search_text))
        out = []
        for raw in re.findall(r"[a-záéíóúñü]+", question.lower()):
            for t in tokenize(raw):
                if t not in known and not t.isdigit():
                    out.append(raw)
        return list(dict.fromkeys(out))

    def _semantic_fuse(self, hits: list[Hit], restrict: set[str] | None) -> tuple[list[Hit], bool]:
        """BM25 + vecinos semánticos precalculados de sus mejores artículos, fusionados con RRF (k=60).

        Un vecino entra con los términos y la cobertura del resultado que lo trajo (es su paráfrasis o su versión en
        otro idioma). Sin vecinos precalculados se devuelve el ranking BM25 intacto (T10)."""
        nb = self.corpus.neighbors
        if not nb or not hits:
            return hits, False
        sem_score: dict[str, float] = {}
        source: dict[str, Hit] = {}
        # Solo se expanden los mejores resultados léxicos: los vecinos de una coincidencia débil («reforma» sola) no
        # deben desplazar a la coincidencia exacta («reforma eléctrica»).
        top_cov = max(h.coverage for h in hits)
        strong = [h for h in hits if h.doc.kind == "articulo" and h.coverage >= top_cov - 1e-9][:3]
        for h in strong:
            for nid, sim in nb.get(h.doc.doc_id, []):
                if restrict is not None and nid not in restrict:
                    continue
                if sim > sem_score.get(nid, 0.0):
                    sem_score[nid], source[nid] = sim, h
        if not sem_score:
            return hits, False
        rrf: dict[str, float] = {}
        by_id = {h.doc.doc_id: h for h in hits}
        for rank, h in enumerate(hits, 1):
            rrf[h.doc.doc_id] = rrf.get(h.doc.doc_id, 0.0) + 1 / (60 + rank)
        for rank, nid in enumerate(sorted(sem_score, key=lambda i: (-sem_score[i], i)), 1):
            rrf[nid] = rrf.get(nid, 0.0) + 1 / (60 + rank)
            src = source[nid]
            if nid in by_id and by_id[nid].coverage < src.coverage:
                old = by_id[nid]  # coincidencia léxica débil, pero es paráfrasis/traducción de un buen resultado
                by_id[nid] = Hit(old.doc, old.bm25, max(old.fuzzy, sem_score[nid]), old.relevance, list(src.matched), src.coverage)
            elif nid not in by_id and nid in self._doc_by_id:
                by_id[nid] = Hit(self._doc_by_id[nid], 0.0, round(sem_score[nid], 4), src.relevance, list(src.matched), src.coverage)
        strong_ids = {h.doc.doc_id for h in strong}
        fused = sorted(by_id.values(), key=lambda h: (h.doc.doc_id not in strong_ids, -rrf.get(h.doc.doc_id, 0.0), h.doc.doc_id))
        return fused[: max(len(hits), 8)], True

    def _as_written(self, question: str, toks) -> list[str]:  # noqa: ANN001
        """Términos internos (raíz o corregidos) → la palabra tal como la escribió la persona."""
        wanted = set(toks)
        out: list[str] = []
        for raw in re.findall(r"[\wáéíóúñü]+", question.lower()):
            mapped, _ = self.index.expand_query(raw)
            if any(m in wanted for m in mapped + tokenize(raw)) and raw not in out:
                out.append(raw)
        return out

    def _content_terms(self, question: str) -> set[str]:
        """Tokens de la pregunta que nombran contenido: sin países, años, números ni palabras de consulta."""
        skip: set[str] = set()
        for kws in COUNTRY_KEYWORDS.values():
            for kw in kws:
                skip.update(tokenize(kw))
        for iso, name in _COUNTRY_ES.items():
            skip.update(tokenize(name))
            skip.add(fold(iso))
        for w in _QUERY_WORDS:
            skip.update(tokenize(w))
        q, _ = self.index.expand_query(question)
        return {t for t in q if t not in skip and not t.isdigit()}

    # ------------------------------------------------------------------ intents
    def _provenance_example(self, scope: TopicBase | None) -> tuple[TopicBase, str, list] | None:
        """Tema real donde una agencia replicada cuenta una vez: (tema, clave de la agencia, sus notas).

        Solo temas cuyo conteo coincide con las claves de origen (sin topes del paquete), para que el ejemplo se pueda
        comprobar nota por nota. Se prefiere el Canal; después, el tema con más notas."""
        candidates = [scope] if scope is not None else list(self.bases.values())
        found: list[tuple[TopicBase, str, list]] = []
        for b in candidates:
            usable = [a for a in b.usable_articles if not a.sponsored_content]
            keys = [a.origin_key for a in usable]
            if b.suspicious_ids or b.independent != len(set(keys)):
                continue
            agencies = [k for k in dict.fromkeys(keys) if k.startswith("agency:") and keys.count(k) >= 2]
            if agencies:
                found.append((b, agencies[0], [a for a in usable if a.origin_key == agencies[0]]))
        if not found:
            return None
        return min(found, key=lambda x: (x[0].category.value != "logistica_canal", -len(x[0].usable_articles), x[0].id))

    def _regla_procedencia(self, req: QueryRequest, scope: TopicBase | None, t0: float) -> QueryResponse:
        """La regla de conteo explicada con un tema real del snapshot y sus notas citadas."""
        f = fold(req.question)
        m = re.search(r"\b(\d{1,2}|" + "|".join(_NUMBER_WORDS) + r")\s+(medios|notas|sitios|portales|diarios|periodicos)\b", f)
        n_asked = (int(m.group(1)) if m.group(1).isdigit() else _NUMBER_WORDS[m.group(1)]) if m else None
        direct = (
            f"**{n_asked} medios que replican la misma agencia cuentan como una sola procedencia independiente, no {n_asked}.**"
            if n_asked and n_asked > 1 else
            "**Varios medios que replican la misma agencia cuentan como una sola procedencia independiente.**"
        )
        rule = (
            "Repetir no es corroborar. Umbral agrupa las notas de un tema por su origen: la agencia cuando la nota la "
            "declara (firma o titular, p. ej. «- Xinhua»); si no, el medio que la publica. Los orígenes desconocidos se "
            "cuentan por dominio y el contenido patrocinado no suma. Para que la evidencia pase de «insuficiente» hacen "
            "falta al menos 2 procedencias independientes."
        )
        example = self._provenance_example(scope)
        if example is None:
            return self._base_resp(
                req, QueryIntent.regla_procedencia, t0, answer_status=AnswerStatus.parcial,
                answer=f"{direct}\n\n{rule}\n\nEn el snapshot {self.corpus.snapshot_id} no hay un tema con una agencia "
                       "replicada para mostrarlo con un ejemplo.",
                missing=["Un tema del snapshot con la misma agencia replicada en varias notas."], coverage=1.0,
            )
        base, agency_key, replicas = example
        agency = replicas[0].origin.strip() or agency_key.split(":", 1)[1]
        agency = agency[:1].upper() + agency[1:]
        notes = base.usable_articles
        lines: list[str] = []
        cites: list[QueryCitation] = []
        for a in sorted(notes, key=lambda a: (a.origin_key != agency_key, a.outlet, a.id)):
            origin = f"agencia {agency}" if a.origin_key == agency_key else f"medio {a.outlet}"
            lines.append(f"- {a.outlet}: «{a.title}» [{a.id}] → procedencia: {origin}")
            cites.append(QueryCitation(evidence_id=a.id, field="title", passage=a.title, title=a.title, url=a.url))
        others = base.independent - 1
        ans = (
            f"{direct}\n\n{rule}\n\n"
            f"**Ejemplo real del snapshot {self.corpus.snapshot_id}:** el tema «{base.display_title}» tiene "
            f"**{len(notes)} notas y {base.independent} procedencias independientes**: las {len(replicas)} notas de "
            f"{agency} cuentan como una sola procedencia y las demás notas suman {others} procedencia(s) más, una por origen distinto.\n\n"
            + "\n".join(lines)
            + "\n\nEl conteo ordena la confianza en la evidencia; no demuestra que el hecho sea cierto "
              "(basado únicamente en titular/metadatos)."
        )
        return self._base_resp(
            req, QueryIntent.regla_procedencia, t0, answer_status=AnswerStatus.respondida, answer=ans, citations=cites,
            hits=[self._hit_model(Hit(self._doc_by_id[c.evidence_id], 0.0, 0.0, 1.0, [], 1.0)) for c in cites[:req.limit]],
            related_topic_ids=[base.id], coverage=1.0, method="regla-procedencia",
        )

    def _agenda(self, req: QueryRequest, agenda: list[TopicSummary], t0: float) -> QueryResponse:
        top = agenda[: max(1, min(req.limit, 5))] if agenda else []
        if not top:
            return self._abstain(req, QueryIntent.agenda, t0, "no hay temas en el snapshot servido.")
        lines = []
        cites: list[QueryCitation] = []
        for i, t in enumerate(top, 1):
            b = self.bases[t.id]
            lines.append(
                f"{i}. **{t.title}**\n"
                f"Puntaje **{score_display(t.score)}** ({t.band.value}) · evidencia {t.evidence_status_label.lower()}"
                f"{' · requiere investigación (prioridad alta con evidencia insuficiente)' if t.needs_investigation else ''}."
            )
            rep = b.representative
            if rep.suspicious_instructions:
                continue
            cites.append(QueryCitation(evidence_id=rep.id, field="title", passage=rep.title, title=rep.title, url=rep.url))
        ans = (
            f"**Temas que merecen revisión** según `{base_rules_version()}` (snapshot {self.corpus.snapshot_id}).\n\n"
            "Basado únicamente en titular/metadatos: el puntaje ordena, no demuestra verdad ni habilita publicación.\n\n"
            + "\n".join(lines)
        )
        return self._base_resp(
            req, QueryIntent.agenda, t0, answer_status=AnswerStatus.respondida, answer=ans, citations=cites,
            related_topic_ids=[t.id for t in top],
            missing=[g for t in top for g in [f"{t.title}: ver verificaciones pendientes en la ficha."] if t.evidence_status.value != "suficiente"][:5],
        )

    def _resumen(self, req: QueryRequest, agenda: list[TopicSummary], t0: float) -> QueryResponse:
        """«Dame el resumen de economía de esta semana»: categoría y periodo son filtros, no términos de búsqueda."""
        f = fold(req.question)
        cat, period = _category(f), _period(f)
        rows = [t for t in agenda if cat is None or t.category.value == cat]
        if cat is None:
            rows = [t for t in rows if not t.out_of_scope]
        undated = 0
        by_detection: set[str] = set()
        if period is not None:
            _, since, until = period
            lo, hi = self.corpus.cutoff - since, self.corpus.cutoff - until
            kept = []
            for t in rows:
                when = t.last_published_at or t.first_published_at
                if when is None and t.id in self.bases:
                    # Sin fecha de publicación (GDELT): se usa la de detección y se dice.
                    detected = [a.detected_at for a in self.bases[t.id].articles if a.detected_at]
                    when = max(detected) if detected else None
                    if when is not None:
                        by_detection.add(t.id)
                if when is None:
                    undated += 1
                elif lo <= when <= hi:
                    kept.append(t)
            rows = kept
        label_cat = CATEGORY_LABELS.get(cat or "", "todas las categorías del reto").lower()
        label_period = period[0] if period else "todo el snapshot"
        cutoff_txt = fmt_date_pa(self.corpus.cutoff)
        if not rows:
            return self._abstain(
                req, QueryIntent.resumen_periodo, t0,
                f"no hay temas de {label_cat} publicados en {label_period} (corte del snapshot: {cutoff_txt}).",
                missing=[f"Notas de {label_cat} en ese periodo; el snapshot solo cubre hasta su corte."],
            )
        top = rows[: max(1, min(req.limit, 5))]
        lines: list[str] = []
        cites: list[QueryCitation] = []
        for i, t in enumerate(top, 1):
            base = self.bases.get(t.id)
            rep = base.representative if base else None
            lines.append(
                f"{i}. **{t.title}** · puntaje {score_display(t.score)} ({t.band.value}) · "
                f"{t.independent_provenances} procedencia(s) independiente(s) · evidencia {t.evidence_status_label.lower()}"
            )
            if rep is not None and not rep.suspicious_instructions:
                cites.append(QueryCitation(evidence_id=rep.id, field="title", passage=rep.title, title=rep.title, url=rep.url))
        ans = (
            f"**Resumen de {label_cat} · {label_period}** (relativo al corte del snapshot, {cutoff_txt}). "
            f"{len(rows)} tema(s); se muestran los {len(top)} de mayor puntaje.\n\n"
            + "\n".join(lines)
            + "\n\nBasado únicamente en titular/metadatos: el puntaje ordena la atención, no demuestra verdad."
            + (f" {len(by_detection & {t.id for t in top})} de estos temas no tienen fecha de publicación: se filtró por fecha de detección." if by_detection & {t.id for t in top} else "")
            + (f" {undated} tema(s) sin ninguna fecha quedaron fuera del filtro de periodo." if undated else "")
        )
        return self._base_resp(
            req, QueryIntent.resumen_periodo, t0,
            answer_status=AnswerStatus.respondida if cites else AnswerStatus.parcial, answer=ans, citations=cites,
            related_topic_ids=[t.id for t in top], coverage=1.0,
            missing=[f"{t.title}: ver verificaciones pendientes en la ficha." for t in top if t.evidence_status.value != "suficiente"][:5],
        )

    def _sismos(self, req: QueryRequest, t0: float) -> QueryResponse:
        """Sismos USGS del paquete: filtra por año/fecha, ordena por magnitud y cita cada evento por su id."""
        f = fold(req.question)
        events = self.corpus.events
        have_years = sorted({int(str(e["time"])[:4]) for e in events})
        years = [int(y) for y in _RE_YEAR.findall(f)]
        missing_years = [y for y in years if y not in have_years]
        if missing_years:
            return self._abstain(
                req, QueryIntent.eventos_sismicos, t0,
                f"el paquete USGS no contiene sismos de {', '.join(map(str, missing_years))} "
                f"(solo {', '.join(map(str, have_years))}). " + SEISMIC_DAMAGE_NOTE,
                missing=[f"Catálogo USGS o SINAPROC del periodo {', '.join(map(str, missing_years))}."],
            )
        sel = [e for e in events if not years or int(str(e["time"])[:4]) in years]
        if re.search(r"\bhoy\b|\bayer\b|esta semana|este mes", f):
            recent = self.corpus.cutoff - timedelta(days=31)
            sel = [e for e in sel if (parse_dt(e["time"]) or recent) >= recent]
            if not sel:
                return self._abstain(
                    req, QueryIntent.eventos_sismicos, t0,
                    "el paquete USGS no tiene sismos cercanos al corte del snapshot "
                    f"({fmt_date_pa(self.corpus.cutoff)}); sus eventos son de {', '.join(map(str, have_years))}. "
                    + SEISMIC_DAMAGE_NOTE,
                    missing=["El reporte sismológico del día (USGS o Instituto de Geociencias de la UP)."],
                )
        if "panam" in f:
            in_pa = [e for e in sel if "panama" in fold(str(e.get("place", "")))]
        else:
            in_pa = sel
        ranked = sorted(sel, key=lambda e: (-float(e["magnitude"]), str(e["id"])))
        top = ranked[:5]
        lines = []
        cites: list[QueryCitation] = []
        for i, e in enumerate(top, 1):
            when = parse_dt(e["time"])
            utc = when.strftime("%Y-%m-%d %H:%M UTC") if when else str(e["time"])
            pa = (when - timedelta(hours=5)).strftime("%d/%m/%Y %H:%M") if when else "—"
            depth = e.get("depth")
            lines.append(
                f"{i}. **M {fmt_es(float(e['magnitude']), 1)}** · {e.get('place') or 'ubicación sin nombre'} · {utc} "
                f"({pa} hora de Panamá) · profundidad {fmt_es(float(depth), 1) if depth is not None else '—'} km [{e['id']}]"
            )
            cites.append(QueryCitation(evidence_id=str(e["id"]), field="magnitude", passage=str(e["magnitude"]),
                                       title=f"USGS {e['id']}: M {e['magnitude']} · {e.get('place') or ''}", url=e.get("url")))
        period = ", ".join(map(str, years)) if years else ", ".join(map(str, have_years))
        biggest = top[0]
        ans = (
            f"**Sismos registrados por USGS en el paquete ({period})**: {len(sel)} en la caja regional"
            + (f", {len(in_pa)} con «Panama» en la ubicación" if "panam" in f else "")
            + f". El mayor fue **M {fmt_es(float(biggest['magnitude']), 1)}** ({biggest.get('place')}).\n\n"
            + "\n".join(lines)
            + f"\n\n{SEISMIC_BOX_NOTE} {SEISMIC_DAMAGE_NOTE}"
        )
        return self._base_resp(
            req, QueryIntent.eventos_sismicos, t0, answer_status=AnswerStatus.respondida, answer=ans, citations=cites,
            missing=["Daños o afectaciones: reporte oficial de SINAPROC; USGS solo mide el evento sísmico."],
            warnings=[SEISMIC_BOX_NOTE], coverage=1.0, matched_terms=["sismo"],
        )

    def _verificaciones(self, req: QueryRequest, scope: TopicBase | None, t0: float) -> QueryResponse:
        base = scope
        hits_models: list[QueryHit] = []
        if base is None:
            hits, _, _ = self.index.search(req.question, limit=5, restrict=self.article_ids)
            hits_models = [self._hit_model(h) for h in hits]
            if hits and hits[0].coverage >= 0.5 and hits[0].doc.cluster_id in self.bases:
                base = self.bases[hits[0].doc.cluster_id or ""]
        if base is None:
            return self._abstain(
                req, QueryIntent.verificaciones, t0,
                "no identifico a qué tema se refiere la pregunta; indica un tema (topicId) o menciona su titular.",
                hits=hits_models,
            )
        pend = base.pending
        cites = [QueryCitation(evidence_id=a.id, field="title", passage=a.title, title=a.title, url=a.url) for a in base.usable_articles[:3]]
        ans = (
            f"Verificaciones pendientes para «{base.display_title}» "
            f"(evidencia {base.system_status.value}, basado únicamente en titular/metadatos):\n"
            + "\n".join(f"- {p}" for p in pend)
        )
        return self._base_resp(
            req, QueryIntent.verificaciones, t0, answer_status=AnswerStatus.respondida, answer=ans, citations=cites,
            missing=pend, related_topic_ids=[base.id], hits=hits_models, contradictions=base.contradictions,
        )

    def _economico(self, req: QueryRequest, scope: TopicBase | None, t0: float) -> QueryResponse:
        f = fold(req.question)
        inds = [k for k, kws in INDICATOR_KEYWORDS.items() if any(kw.strip() in f for kw in kws)]
        countries = [c for c, kws in COUNTRY_KEYWORDS.items() if any(kw in f for kw in kws)] or ["PAN"]
        years = [int(y) for y in _RE_YEAR.findall(f)]
        asked_today = bool(re.search(r"\bhoy\b|\bactual(es|mente)?\b|\beste ano\b|\bahora\b", f))
        unknown = self._unknown_entities(req.question, scope)
        if unknown:
            return self._abstain(
                req, QueryIntent.contexto_economico, t0,
                f"no puedo vincular «{', '.join(unknown)}» con ningún país o indicador oficial del paquete "
                "(Panamá, Costa Rica, Colombia, República Dominicana, México, Guatemala).",
                missing=[f"Un indicador oficial pertinente para: {', '.join(unknown)}."],
            )
        if not inds and scope is not None and scope.indicators:
            inds = sorted({p.indicator_id for p in scope.indicators})
            countries = sorted({p.country_iso3 for p in scope.indicators})
        if not inds:
            avail = ", ".join(INDICATOR_LABEL_ES.values())
            return self._abstain(
                req, QueryIntent.contexto_economico, t0,
                "no identifico qué indicador oficial pides.",
                missing=[f"Indica un indicador entre: {avail}."],
            )
        lines: list[str] = []
        cites: list[QueryCitation] = []
        missing: list[str] = []
        selected_ids: set[str] = set()
        found = 0
        for iso in countries:
            for ind in inds:
                rows = sorted(
                    (p for p in self.corpus.indicators.values() if p.country_iso3 == iso and p.indicator_id == ind),
                    key=lambda p: p.year,
                )
                label = f"{INDICATOR_LABEL_ES.get(ind, ind)} de {_COUNTRY_ES.get(iso, iso)}"
                if years:
                    for y in years:
                        row = next((p for p in rows if p.year == y), None)
                        if row is None:
                            missing.append(f"{label} {y}: el año no existe en la cuadrícula del paquete (2010–2024).")
                        elif row.is_missing:
                            missing.append(f"{label} {y}: valor ausente en la fuente (se conserva como nulo, no se rellena).")
                        else:
                            found += 1
                            selected_ids.add(row.id)
                            lines.append(_econ_line(f"{label}, {y}", row))
                            cites.extend(_ind_cites(row))
                else:
                    valid = [p for p in rows if not p.is_missing and p.year <= self.corpus.cutoff.year]
                    if not valid:
                        missing.append(f"{label}: sin valores disponibles en el paquete.")
                        continue
                    row = valid[-1]
                    found += 1
                    selected_ids.add(row.id)
                    lines.append(_econ_line(f"{label}, último año con dato {row.year}", row))
                    cites.extend(_ind_cites(row))
                    later = [p for p in rows if p.is_missing and p.year > row.year]
                    if later:
                        missing.append(f"{label}: {', '.join(str(p.year) for p in later)} sin valor en la fuente.")
        if found == 0:
            return self._abstain(
                req, QueryIntent.contexto_economico, t0,
                "el paquete oficial no contiene el valor solicitado.", missing=missing or None,
            )
        extra = " Se pidió un dato «de hoy»: el paquete solo tiene valores anuales históricos." if asked_today else ""
        ans = (
            "Contexto oficial (Banco Mundial, snapshot " + self.corpus.snapshot_id + "):\n" + "\n".join(lines) + extra
        )
        status = AnswerStatus.respondida if not missing else AnswerStatus.parcial
        ranked_hits, _, _ = self.index.search(req.question, limit=req.limit, restrict=selected_ids)
        return self._base_resp(
            req, QueryIntent.contexto_economico, t0, answer_status=status, answer=ans, citations=cites,
            missing=missing, related_topic_ids=[scope.id] if scope else [],
            hits=[self._hit_model(hit) for hit in ranked_hits],
            matched_terms=ranked_hits[0].matched if ranked_hits else [],
            coverage=round(ranked_hits[0].coverage, 3) if ranked_hits else 0.0,
        )

    def _busqueda(self, req: QueryRequest, scope: TopicBase | None, t0: float) -> QueryResponse:
        restrict = None
        if scope is not None:
            restrict = {a.id for a in scope.articles} | {p.id for p in scope.indicators}
        future_years = {year for year in _RE_YEAR.findall(req.question) if int(year) > self.corpus.cutoff.year}
        if future_years:
            future_ids = {a.id for a in self.corpus.articles.values()
                          if not a.suspicious_instructions and future_years <= set(_RE_YEAR.findall(a.title))}
            restrict = future_ids if restrict is None else restrict & future_ids
            if not restrict:
                return self._abstain(
                    req, QueryIntent.busqueda, t0,
                    "la consulta pide un año futuro que no aparece en ningún titular pertinente del corpus.",
                    missing=["Una fuente que mencione explícitamente el periodo futuro solicitado; no se predicen resultados."],
                )
        hits, qtoks, unmatched = self.index.search(req.question, limit=max(req.limit, 5), restrict=restrict)
        hit_models = [self._hit_model(h) for h in hits[: req.limit]]
        if not hits:
            return self._abstain(
                req, QueryIntent.busqueda, t0, "ningún documento del corpus coincide con los términos de la consulta.",
                missing=[f"Cobertura para: {', '.join(self._as_written(req.question, unmatched or qtoks)) or req.question}."],
            )
        best = hits[0]
        coverage = round(best.coverage, 3)
        if coverage < 0.5:
            return self._abstain(
                req, QueryIntent.busqueda, t0,
                f"la mejor coincidencia cubre menos de la mitad de los términos de la consulta (términos sin respaldo: "
                f"{', '.join(self._as_written(req.question, set(qtoks) - set(best.matched))) or '—'}).",
                hits=hit_models, coverage=coverage, matched=best.matched,
                missing=[f"Evidencia que mencione: {', '.join(self._as_written(req.question, set(qtoks) - set(best.matched)))}."],
            )
        # La cobertura se decide con BM25; después se suman paráfrasis y versiones en otro idioma (RRF).
        hits, semantic = self._semantic_fuse(hits, restrict)
        hit_models = [self._hit_model(h) for h in hits[: req.limit]]
        # ¿pide una cifra? solo se responde si algún titular relevante la contiene
        wants_number = bool(_RE_NUMERIC.search(fold(req.question)))
        arts = [h for h in hits if h.doc.kind == "articulo"]
        usable = [h for h in arts if not self.corpus.articles[h.doc.doc_id].suspicious_instructions and h.coverage >= 0.5]
        warnings: list[str] = []
        for h in arts:
            if self.corpus.articles[h.doc.doc_id].suspicious_instructions:
                warnings.append(
                    f"La fuente {h.doc.doc_id} contiene instrucciones dirigidas a un agente: se trató como contenido no confiable y no se usó."
                )
        ind_hits = [h for h in hits if h.doc.kind == "indicador" and h.coverage >= 0.5]
        # Regla general: solo se cita lo que comparte un término de contenido con la pregunta (no basta «Panamá»
        # ni el año): así no aparecen «rellenos» como población o desempleo en una pregunta sobre sismos.
        content = self._content_terms(req.question)
        if content:
            usable = [h for h in usable if set(h.matched) & content]
            ind_hits = [h for h in ind_hits if set(h.matched) & content]
        if not usable and not ind_hits:
            return self._abstain(
                req, QueryIntent.busqueda, t0, "las únicas coincidencias son fuentes no confiables o de baja cobertura.",
                hits=hit_models, coverage=coverage, matched=best.matched, warnings=warnings,
            )
        if wants_number and not any(re.search(r"\d", self.corpus.articles[h.doc.doc_id].title) for h in usable) and not ind_hits:
            return self._abstain(
                req, QueryIntent.busqueda, t0,
                "los titulares relacionados no contienen la cifra solicitada y no hay serie oficial pertinente.",
                hits=hit_models, coverage=coverage, matched=best.matched, warnings=warnings,
                missing=["La cifra solicitada con su fuente primaria u oficial."],
            )

        kind = _number_kind(fold(req.question))
        if kind is not None and not (kind[0] == "un porcentaje" and ind_hits):
            label, _, evidence_re, need = kind
            with_figure = [h for h in usable if evidence_re.search(fold(self.corpus.articles[h.doc.doc_id].title))]
            if _RE_TODAY.search(fold(req.question)):
                recent = self.corpus.cutoff - timedelta(hours=48)
                with_figure = [h for h in with_figure if (self._when(h) or recent) >= recent]
            if not with_figure:
                return self._abstain(
                    req, QueryIntent.busqueda, t0,
                    f"ningún titular pertinente contiene {label}"
                    + (" publicado en las 48 horas previas al corte" if _RE_TODAY.search(fold(req.question)) else "")
                    + "; un número cualquiera en el titular no responde la pregunta.",
                    hits=hit_models, coverage=coverage, matched=best.matched, warnings=warnings, missing=[need],
                )

        # agrupar por cluster; tomar el cluster del mejor artículo utilizable
        lines: list[str] = []
        cites: list[QueryCitation] = []
        contradictions: list[Contradiction] = []
        related: list[str] = []
        status = AnswerStatus.respondida if coverage >= 0.75 else AnswerStatus.parcial
        missing: list[str] = []
        used_clusters: list[str] = []
        usable_ids = {h.doc.doc_id for h in usable}
        for h in usable[:4]:
            a = self.corpus.articles[h.doc.doc_id]
            if a.cluster_id and a.cluster_id not in used_clusters:
                used_clusters.append(a.cluster_id)
        for cid in used_clusters[:3]:
            base = self.bases.get(cid)
            if base is None:
                continue
            related.append(cid)
            seen_keys: set[str] = set()
            for a in base.usable_articles:
                if a.origin_key in seen_keys:
                    continue
                if content and not (set(tokenize(a.title)) & content) and a.id not in usable_ids:
                    continue  # mismo grupo, pero sin un término de la pregunta: no se cita
                seen_keys.add(a.origin_key)
                if len(seen_keys) > 3:
                    break
                when = (
                    f"publicado {fmt_date_pa(a.published_at)}"
                    if a.published_at
                    else f"fecha de publicación desconocida; detectado {fmt_date_pa(a.detected_at)}"
                )
                lines.append(f"- {a.outlet} ({when}): «{a.title}» [{a.id}]")
                cites.append(QueryCitation(evidence_id=a.id, field="title", passage=a.title, title=a.title, url=a.url))
            note = (
                f"  ({len(base.usable_articles)} nota(s), {base.independent} procedencia(s) independiente(s); "
                f"evidencia {base.system_status.value})"
            )
            lines.append(note)
            if base.is_recirculation:
                lines.append(f"  Atención: posible noticia antigua recirculada ({base.recirculation_reason or 'fecha original anterior'}).")
            contradictions.extend(base.contradictions)
            missing.extend(base.pending[:3])
        # QA TVN 3.4: la misma magnitud con valores distintos entre notas recuperadas juntas (ES/EN, temas distintos).
        known_ids = {c.id for c in contradictions}
        pool = [self.corpus.articles[c.evidence_id] for c in cites if c.evidence_id in self.corpus.articles]
        pool += [self.corpus.articles[h.doc.doc_id] for h in usable]
        for c in cross_contradictions(pool):
            if c.id not in known_ids:
                contradictions.insert(0, c)
        for h in ind_hits[:2]:
            p = self.corpus.indicators[h.doc.doc_id]
            if p.is_missing:
                missing.append(f"{p.indicator_name} {p.country_iso3} {p.year}: valor ausente en la fuente.")
                continue
            lines.append(f"- Banco Mundial: {_ind_text(p)}")
            cites.extend(_ind_cites(p))
        if contradictions:
            status = AnswerStatus.contradiccion
            lines.append("Versiones incompatibles (no se elige una; revisión pendiente):")
            for c in contradictions:
                lines.append(f"  · {c.description}")
                for v in c.versions:
                    when = (f"publicado {fmt_date_pa(v.published_at)}" if v.published_at
                            else f"detectado {fmt_date_pa(v.detected_at)}" if v.detected_at else "sin fecha")
                    lines.append(f"    - {v.outlet} ({when}): «{v.statement}» [{v.evidence_id}]")
        ans = (
            "Lo que reporta el corpus (basado únicamente en titular/metadatos; no se leyó el artículo completo):\n"
            + "\n".join(lines)
        )
        return self._base_resp(
            req, QueryIntent.busqueda, t0, answer_status=status, answer=ans, citations=cites, hits=hit_models,
            contradictions=contradictions, missing=list(dict.fromkeys(missing)), related_topic_ids=related,
            warnings=warnings, coverage=coverage, matched_terms=best.matched,
            method="bm25+rapidfuzz+semantico-rrf" if semantic else "bm25+rapidfuzz",
        )


def _econ_line(label: str, p: IndicatorPoint) -> str:
    """Valor, año, unidad, fuente y URL: la respuesta dice de dónde sale la cifra, no solo la cita."""
    url = f" · {p.source_url}" if p.source_url else ""
    return f"- {label}: {format_value_es(p.value, p.unit)} (dato anual, no de hoy). Fuente: Banco Mundial, {p.indicator_id}{url}"


def _ind_text(p: IndicatorPoint) -> str:
    if p.is_missing:
        return f"{p.indicator_name}, {p.country_iso3} {p.year}: valor ausente en la fuente."
    return f"{p.indicator_name}, {p.country_iso3} {p.year}: {format_value_es(p.value, p.unit)} (dato anual de referencia, no de hoy)."


def _ind_cites(p: IndicatorPoint) -> list[QueryCitation]:
    return [
        QueryCitation(evidence_id=p.id, field="value", passage=exact_str(p.value) if p.value is not None else "", title=_ind_text(p), url=p.source_url),
        QueryCitation(evidence_id=p.id, field="year", passage=str(p.year), title=_ind_text(p), url=p.source_url),
    ]


__all__ = ["QueryEngine", "tokenize", "DataMode"]
