"""Borradores: paquete de evidencia, validación (citas/alcance/formato/límites) y plantilla con citas."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .cifras import exact_str, score_display
from .models import (
    CATEGORY_LABELS,
    Claim,
    ClaimType,
    EditorialPackage,
    ValidationIssue,
    ValidationReport,
)
from .retrieval import fold
from .security import leaks_secret
from .topics import HEADLINE_NOTICE, MASKED_TITLE, TopicBase
from .util import fmt_date_pa, marker_ids, strip_markers, word_count

BRIEF_MAX_WORDS = 250
COPY_MAX_WORDS = 80
SCRIPT_WPS = 2.5  # palabras por segundo (guion hablado en español)
SCRIPT_MIN_S, SCRIPT_MAX_S = 45.0, 60.0
SCRIPT_MIN_WORDS = int(SCRIPT_MIN_S * SCRIPT_WPS)  # 112
SCRIPT_MAX_WORDS = int(SCRIPT_MAX_S * SCRIPT_WPS)  # 150
HEADLINE_PREFIX = "Basado únicamente en titular/metadatos."


# Fuente primaria por categoría: las preguntas de investigación dicen a quién llamar, no solo «una fuente oficial».
PRIMARY_SOURCE: dict[str, tuple[str, str]] = {
    "logistica_canal": ("la Autoridad del Canal de Panamá (ACP)", "avisos a navieras y estadísticas de tránsito"),
    "economia": ("el MEF y la Contraloría General", "informes de ejecución presupuestaria y del INEC"),
    "servicios_publicos": ("la ASEP", "resoluciones tarifarias y reportes de interrupciones"),
    "turismo": ("la Autoridad de Turismo de Panamá (ATP)", "estadísticas de llegada de visitantes"),
    "eventos_naturales": ("SINAPROC", "informes de afectación y alertas oficiales"),
    "regulacion": ("la Gaceta Oficial y la Asamblea Nacional", "texto del proyecto o de la norma sancionada"),
    "indeterminado": ("la institución responsable del tema", "documento oficial que respalde el hecho"),
}
SCRIPT_NOTES_LABEL = "NOTAS DE PRODUCCIÓN"


def _tidy(text: str) -> str:
    """Puntuación limpia al unir listas: sin «..» ni «;.» (se respeta «…» y el texto del titular)."""
    text = re.sub(r"(?<![.…])\.\s*\.(?!\.)", ".", text)
    text = re.sub(r"[;,]\s*\.", ".", text)
    return text


def _contract(text: str) -> str:
    """Contracciones obligatorias en el texto de la plantilla: «a el MEF» → «al MEF», «de el» → «del».

    Solo con «el» en minúscula: «a El Salvador» o «de El Siglo» son nombres propios y no se contraen."""
    text = re.sub(r"\b([aA]) el\b", lambda m: "al" if m.group(1) == "a" else "Al", text)
    return re.sub(r"\b([dD]e) el\b", lambda m: "del" if m.group(1) == "de" else "Del", text)


def _is_spanish(language: str | None) -> bool:
    return (language or "es").lower().startswith("es")


def spoken_part(script: str) -> str:
    """Lo que se lee al aire: el guion sin las notas de producción."""
    return script.split(SCRIPT_NOTES_LABEL)[0].replace("GUION:", "").strip()


def research_questions(base: TopicBase) -> list[str]:
    """Tres preguntas según la categoría y lo que falta (fuente primaria, fecha, cifras, contradicciones)."""
    name, doc = PRIMARY_SOURCE.get(base.category.value, PRIMARY_SOURCE["indeterminado"])
    qs = [f"¿Qué dice exactamente {name} sobre este hecho? Pedir {doc}."]
    if base.contradictions:
        qs.append("¿Por qué difieren las cifras entre medios: es una actualización o una contradicción? Comparar fechas y fuente primaria.")
    elif base.is_recirculation or base.first_published is None:
        qs.append("¿Cuál es la fecha original del hecho? Si es una nota recirculada, ¿qué cambió desde entonces?")
    elif base.independent < 2:
        qs.append("¿Qué segunda fuente independiente (no una réplica de la misma agencia) confirma el hecho?")
    else:
        qs.append("¿Coinciden los medios en los datos clave o solo replican el mismo titular?")
    by_cat = {
        "logistica_canal": "¿Cómo afecta a navieras, exportadores y al ingreso del Canal, según datos de la ACP de este año?",
        "economia": "¿Qué impacto tiene en el bolsillo de los panameños según cifras del INEC o del MEF, y de qué periodo son?",
        "servicios_publicos": "¿Qué comunidades o usuarios se ven afectados y qué plazos o tarifas ha fijado la ASEP?",
        "turismo": "¿Cómo se compara con las estadísticas de la ATP del mismo periodo del año anterior?",
        "eventos_naturales": "¿Hay afectados, daños o evacuaciones confirmados por SINAPROC? Sin ese reporte no se informan cifras.",
        "regulacion": "¿En qué etapa está la norma (debate, sanción, reglamentación) y a quién obliga?",
    }
    qs.append(by_cat.get(base.category.value, "¿Qué dato oficial dimensiona el alcance del tema y de qué periodo proviene?"))
    return qs

ARTICLE_FIELDS = ("title", "outlet", "publishedAt", "detectedAt", "url", "origin", "category")
INDICATOR_FIELDS = ("value", "unit", "year", "countryIso3", "indicatorName")


@dataclass
class EvidencePack:
    """Evidencia recuperada del corpus para un tema: lo único que puede citar un borrador."""

    items: dict[str, dict[str, str]] = field(default_factory=dict)
    kinds: dict[str, str] = field(default_factory=dict)
    excluded: set[str] = field(default_factory=set)  # fuentes con instrucciones: no citables
    headline_only: bool = True


def build_pack(base: TopicBase) -> EvidencePack:
    pack = EvidencePack()
    for a in base.articles:
        if a.suspicious_instructions:
            pack.excluded.add(a.id)
            continue
        pack.items[a.id] = {
            "title": a.title,
            "outlet": a.outlet,
            "publishedAt": a.published_at.isoformat() if a.published_at else "",
            "detectedAt": a.detected_at.isoformat() if a.detected_at else "",
            "url": a.url,
            "origin": a.origin,
            "category": a.category.value,
        }
        pack.kinds[a.id] = "articulo"
    for p in base.indicators:
        if p.is_missing or p.value is None:
            continue
        pack.items[p.id] = {
            "value": exact_str(p.value),
            "unit": p.unit or "",
            "year": str(p.year),
            "countryIso3": p.country_iso3,
            "indicatorName": p.indicator_name,
        }
        pack.kinds[p.id] = "indicador"
    return pack


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", fold(s)).strip()


def _numbers(text: str) -> set[float]:
    out: set[float] = set()
    for tok in re.findall(r"\d[\d.,]*\d|\d", text):
        cands = {tok.replace(",", "."), tok.replace(".", "").replace(",", "."), tok.replace(",", "")}
        for c in cands:
            try:
                out.add(float(c))
            except ValueError:
                pass
    return out


def validate_claims(claims: list[Claim], pack: EvidencePack) -> tuple[list[Claim], list[ValidationIssue]]:
    """Valida IDs de cita, campo, pasaje, alcance y cifras. Devuelve afirmaciones aceptadas y problemas."""
    issues: list[ValidationIssue] = []
    kept: list[Claim] = []
    seen_ids: set[str] = set()
    for c in claims:
        problems: list[ValidationIssue] = []

        def bad(code: str, msg: str, _c: Claim = c, _p: list[ValidationIssue] = problems) -> None:
            _p.append(ValidationIssue(code=code, severity="error", message=msg, claim_id=_c.id))

        if c.id in seen_ids:
            bad("id_duplicado", f"El ID de afirmación {c.id} está repetido.")
        seen_ids.add(c.id)
        if not c.text.strip():
            bad("afirmacion_vacia", "Afirmación sin texto.")
        if c.type in (ClaimType.hecho, ClaimType.declaracion, ClaimType.inferencia) and not c.citations:
            bad("sin_cita", f"La afirmación {c.id} ({c.type.value}) requiere al menos una cita.")
        cited_text: list[str] = []
        for ct in c.citations:
            if ct.evidence_id in pack.excluded:
                bad("fuente_no_confiable", f"{ct.evidence_id} contiene instrucciones y no es citable.")
                continue
            item = pack.items.get(ct.evidence_id)
            if item is None:
                bad("cita_inexistente", f"El ID de evidencia {ct.evidence_id} no existe en el alcance del tema.")
                continue
            if ct.field not in item:
                bad("campo_inexistente", f"El campo «{ct.field}» no existe en {ct.evidence_id}.")
                continue
            value = item[ct.field]
            if ct.passage is not None and ct.passage.strip():
                if _norm(ct.passage) not in _norm(value):
                    bad("pasaje_no_encontrado", f"El pasaje citado no aparece en {ct.evidence_id}.{ct.field}.")
                    continue
            cited_text.append(value)
            if ct.passage:
                cited_text.append(ct.passage)
        if c.type in (ClaimType.hecho, ClaimType.declaracion) and cited_text and not problems:
            allowed = _numbers(" ".join(cited_text))
            # Presentación periodística de una cifra citada (1 decimal, millones): sigue respaldada por el valor exacto.
            allowed |= {round(x / scale, k) for x in list(allowed) for scale in (1, 1_000_000) for k in (0, 1, 2)}
            for tok in re.findall(r"\d[\d.,]*\d|\d", c.text):
                cand = _numbers(tok)
                if cand and not (cand & allowed):
                    bad("cifra_no_respaldada", f"La cifra «{tok}» de la afirmación {c.id} no aparece en lo citado.")
                    break
        if problems:
            issues.extend(problems)
        else:
            kept.append(c)
    return kept, issues


def validate_package(pkg: EditorialPackage, pack: EvidencePack, *, proposed_claims: int | None = None) -> tuple[EditorialPackage, ValidationReport]:
    """Valida formato, límites y citas. Las afirmaciones inválidas se rechazan (no se muestran)."""
    issues: list[ValidationIssue] = []
    claims, claim_issues = validate_claims(pkg.claims, pack)
    issues.extend(claim_issues)
    rejected = sorted({i.claim_id for i in claim_issues if i.claim_id})
    total_claims = proposed_claims if proposed_claims is not None else len(pkg.claims)
    valid_ids = {c.id for c in claims}

    def fix_markers(text: str, name: str) -> str:
        bad = [m for m in marker_ids(text) if m not in valid_ids]
        if bad:
            issues.append(
                ValidationIssue(code="marcador_invalido", severity="warning", message=f"{name}: marcadores a afirmaciones inexistentes o rechazadas ({', '.join(sorted(set(bad)))}); se retiraron.")
            )
            for m in set(bad):
                text = re.sub(rf"\s*\[{m}\]", "", text)
        return text

    brief = fix_markers(pkg.brief, "brief")
    script = fix_markers(pkg.script, "guion")
    copy = fix_markers(pkg.social_copy, "copy")

    if not claims:
        issues.append(ValidationIssue(code="sin_afirmaciones_validas", severity="error", message="Ninguna afirmación pasó la validación de citas."))

    # aviso obligatorio titular/metadatos
    headline_only = pack.headline_only
    notice = HEADLINE_NOTICE if headline_only else None
    if headline_only and fold(HEADLINE_PREFIX.rstrip(".")) not in fold(brief):
        brief = f"{HEADLINE_PREFIX} {brief}".strip()

    wc = {"brief": word_count(strip_markers(brief)), "script": word_count(strip_markers(spoken_part(script))), "socialCopy": word_count(strip_markers(copy))}
    if wc["brief"] > BRIEF_MAX_WORDS:
        issues.append(ValidationIssue(code="brief_excede_limite", severity="error", message=f"El brief tiene {wc['brief']} palabras (máximo {BRIEF_MAX_WORDS})."))
    if wc["socialCopy"] > COPY_MAX_WORDS:
        issues.append(ValidationIssue(code="copy_excede_limite", severity="error", message=f"El copy tiene {wc['socialCopy']} palabras (máximo {COPY_MAX_WORDS})."))
    secs = wc["script"] / SCRIPT_WPS
    if not (SCRIPT_MIN_S <= secs <= SCRIPT_MAX_S):
        issues.append(ValidationIssue(code="guion_fuera_de_rango", severity="error", message=f"El guion dura ≈{secs:.0f} s ({wc['script']} palabras); debe estar entre 45 y 60 s (≈{SCRIPT_MIN_WORDS}–{SCRIPT_MAX_WORDS} palabras)."))
    qs = [q.strip() for q in pkg.research_questions if q.strip()]
    if len(qs) != 3:
        issues.append(ValidationIssue(code="preguntas_invalidas", severity="error", message=f"Se requieren exactamente 3 preguntas de investigación (hay {len(qs)})."))
    if not [p for p in pkg.pending_verifications if p.strip()]:
        issues.append(ValidationIssue(code="sin_verificaciones", severity="error", message="Falta la lista de verificaciones pendientes."))
    if not pkg.proposed_title.strip() or len(pkg.proposed_title) > 160:
        issues.append(ValidationIssue(code="titulo_invalido", severity="error", message="El título propuesto está vacío o supera 160 caracteres."))
    if not pkg.public_interest_angle.strip():
        issues.append(ValidationIssue(code="sin_enfoque", severity="error", message="Falta el enfoque de interés público."))
    if not marker_ids(brief) and claims:
        issues.append(ValidationIssue(code="brief_sin_marcadores", severity="warning", message="El brief no referencia afirmaciones ([c1]…): las citas no son visibles en el texto."))
    for name, txt in (("brief", brief), ("guion", script), ("copy", copy), ("título", pkg.proposed_title)):
        if leaks_secret(txt):
            issues.append(ValidationIssue(code="posible_fuga_de_secreto", severity="error", message=f"El texto de {name} parece contener un secreto/credencial."))
    if claims and all(c.type == ClaimType.hipotesis for c in claims):
        issues.append(ValidationIssue(code="solo_hipotesis", severity="warning", message="Todas las afirmaciones son hipótesis; no hay hechos ni declaraciones respaldadas."))

    cited = [c for c in claims if c.citations]
    coverage = (len(cited) / total_claims) if total_claims else 0.0
    factual_types = (ClaimType.hecho, ClaimType.declaracion)
    factual_proposed = [c for c in pkg.claims if c.type in factual_types]
    factual_ok = [c for c in claims if c.type in factual_types and c.citations]
    factual_cov = round(len(factual_ok) / len(factual_proposed), 3) if factual_proposed else None
    ok = not [i for i in issues if i.severity == "error"]
    cleaned = pkg.model_copy(
        update={
            "brief": brief,
            "script": script,
            "social_copy": copy,
            "claims": claims,
            "research_questions": qs,
            "headline_only": headline_only,
            "headline_only_notice": notice,
        }
    )
    report = ValidationReport(
        ok=ok,
        issues=issues,
        rejected_claim_ids=rejected,
        word_counts=wc,
        script_seconds_estimate=round(secs, 1),
        citation_coverage=round(coverage, 3),
        factual_citation_coverage=factual_cov,
    )
    return cleaned, report


# --------------------------------------------------------------------------- plantilla


def _q(title: str) -> str:
    return f"«{title.strip()}»"


def build_template_package(base: TopicBase, *, score: float, band: str, status: str) -> EditorialPackage:
    """Paquete editorial determinista con citas (modo plantilla / sin conexión)."""
    claims = [c.model_copy(deep=True) for c in base.claims]
    # reenumerar de forma estable c1..cN
    for i, c in enumerate(claims, 1):
        c.id = f"c{i}"
    n = len(claims)
    decl = [c for c in claims if c.type == ClaimType.declaracion]
    facts = [c for c in claims if c.type == ClaimType.hecho]
    if base.independent >= 2 and len(decl) >= 2:
        n += 1
        claims.append(
            Claim(
                id=f"c{n}",
                type=ClaimType.inferencia,
                text=(
                    f"Dado que {len(decl)} procedencias independientes reportan el mismo evento, es razonable inferir "
                    "que el hecho fue observado más de una vez; esto no prueba su veracidad."
                ),
                citations=[c.citations[0] for c in decl[:2]],
            )
        )
    n += 1
    claims.append(
        Claim(
            id=f"c{n}",
            type=ClaimType.hipotesis,
            text=(
                f"Hipótesis a verificar: el tema podría tener interés público en {CATEGORY_LABELS[base.category.value].lower()} "
                "para Panamá; el corpus no lo confirma."
            ),
            citations=[],
        )
    )
    rep = base.representative if not base.representative.suspicious_instructions else (base.usable_articles[0] if base.usable_articles else base.representative)
    first_decl = decl[0] if decl else None
    outlet = rep.outlet if not rep.suspicious_instructions else "una fuente no confiable"
    title = rep.title if not rep.suspicious_instructions else MASKED_TITLE
    pending = list(base.pending)[:6] or ["Confirmar el hecho con la fuente primaria."]
    status_txt = {"insuficiente": "insuficiente", "parcial": "parcial", "suficiente": "suficiente para el borrador"}[status]
    first_marker = f" [{first_decl.id}]" if first_decl else ""

    parts = [
        f"{HEADLINE_PREFIX}",
        f"{outlet} reporta en su titular {_q(title)}{first_marker}.",
    ]
    for c in decl[1:3]:
        parts.append(f"También lo reporta {c.text.split(' reporta')[0]} [{c.id}].")
    for c in facts[:1]:
        parts.append(f"Contexto oficial: {c.text} [{c.id}]")
    if base.is_recirculation:
        parts.append(f"Atención: posible noticia antigua recirculada ({base.recirculation_reason or 'fecha original anterior'}).")
    if base.contradictions:
        parts.append("Hay versiones incompatibles entre fuentes; se muestran ambas y la revisión está pendiente, sin elegir una.")
    parts.append(
        f"Evidencia {status_txt}; puntaje de atención {score_display(score)} ({band}), que ordena la revisión y no demuestra verdad."
    )
    parts.append("Falta verificar: " + "; ".join(p.rstrip(". ") for p in pending[:3]) + ".")
    brief = _tidy(" ".join(parts))
    while word_count(strip_markers(brief)) > 235 and len(parts) > 4:
        parts.pop(-3 if len(parts) > 5 else -2)
        brief = _tidy(" ".join(parts))

    when = fmt_date_pa(base.first_published, unknown="sin fecha de publicación confirmada")
    src = PRIMARY_SOURCE.get(base.category.value, PRIMARY_SOURCE["indeterminado"])
    # GUION: lo que lee el presentador. Solo hechos atribuidos (quién lo publicó y cuándo), nada sin fuente.
    foreign = not rep.suspicious_instructions and not _is_spanish(rep.language)
    if foreign:
        # No se lee al aire un titular en otro idioma ni se inventa una traducción: se atribuye y el original va a notas.
        spoken = [
            f"Un medio internacional, {outlet}, reporta que hay novedades sobre este tema{first_marker}; "
            "el titular original está en otro idioma y su traducción debe verificarse antes de citarlo al aire.",
        ]
    else:
        spoken = [
            f"{outlet} informó en su titular que {title.strip().rstrip(' .')}{first_marker}.",
        ]
    for c in decl[1:3]:
        spoken.append(f"La información también aparece en {c.text.split(' reporta')[0]} [{c.id}].")
    if facts:
        spoken.append(f"Como contexto, {facts[0].text.rstrip('.')} [{facts[0].id}].")
    spoken.append(f"La publicación original está fechada el {when}." if base.first_published else "La fecha original de la publicación todavía no está confirmada.")
    pads = [
        "Hasta este momento, lo que se conoce proviene de los titulares publicados y no del texto completo de las notas.",
        f"La confirmación de este dato corresponde a {src[0]}, la fuente primaria para este tipo de información.",
        "Es una información en desarrollo y cualquier cifra adicional se dará con su fuente y su fecha.",
        # Solo tiene sentido con más de una procedencia: con una sola fuente no hay «versiones entre medios».
        *(["Si hay versiones distintas entre medios, se informarán ambas con su fuente, sin dar una por cierta."]
          if base.independent >= 2 else []),
        "Ampliaremos esta información en cuanto exista confirmación de una fuente oficial.",
        "Les recordamos que en TVN cada dato se atribuye a la fuente que lo publicó.",
        "Mientras tanto, conviene tomar estos datos con cautela y esperar la versión oficial.",
        "Cuando exista un documento oficial, se citará con su fecha y con la institución que lo emite.",
    ]
    pi = 0
    while word_count(strip_markers(" ".join(spoken))) < SCRIPT_MIN_WORDS + 2 and pi < len(pads):
        spoken.append(pads[pi])
        pi += 1
    while word_count(strip_markers(" ".join(spoken))) > SCRIPT_MAX_WORDS - 2 and len(spoken) > 2:
        spoken.pop(-2)
    guion = " ".join(spoken)
    if word_count(strip_markers(guion)) > SCRIPT_MAX_WORDS - 2:  # titular muy largo
        guion = " ".join(strip_markers(guion).split()[: SCRIPT_MAX_WORDS - 6]) + "."
    notes = [f"Evidencia {status_txt}; basado únicamente en titular/metadatos."]
    if foreign:
        notes.append(f"Titular original ({rep.language}): {_q(title)}{first_marker}.")
    notes += [f"Verificar: {p.rstrip('.')}." for p in pending[:3]]
    notes.append(f"Pendiente: solicitar confirmación a {src[0]} ({src[1]}).")
    if base.contradictions:
        notes.append("Hay versiones incompatibles entre fuentes: no leer una cifra hasta resolverlas.")
    script = _tidy(f"GUION: {_contract(guion)}\n\n{SCRIPT_NOTES_LABEL}: " + _contract(" ".join(notes)))

    copy_core = f"{title.strip()}"
    cwords = copy_core.split()
    if len(cwords) > 38:
        copy_core = " ".join(cwords[:38]) + "…"
    copy = (
        f"Borrador para revisión: {outlet} reporta {_q(copy_core)}{first_marker}. "
        f"Evidencia {status_txt}. Basado únicamente en titular/metadatos; pendiente de verificación."
    )

    angle = (
        f"Posible interés público en {CATEGORY_LABELS[base.category.value].lower()} para Panamá; el alcance real "
        "depende de verificar la fuente primaria y la fecha original."
    )
    qs = research_questions(base)
    limitations = [
        "Basado únicamente en titular/metadatos.",
        "Las citas verifican estructura, no sustento: requieren revisión humana.",
        "Borrador construido mediante plantilla; no sustituye la redacción editorial.",
    ]
    return EditorialPackage(
        proposed_title=f"Revisión: {title.strip()}"[:160],
        brief=brief,
        public_interest_angle=angle,
        research_questions=qs,
        pending_verifications=pending,
        script=script,
        social_copy=copy,
        claims=claims,
        headline_only=True,
        headline_only_notice=HEADLINE_NOTICE,
        limitations=limitations,
    )
