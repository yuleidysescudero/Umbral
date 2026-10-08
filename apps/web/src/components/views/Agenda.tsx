import { useEffect, useId, useRef, useState } from 'react';
import { ArrowRight, ChevronDown, FileSearch, GitCompare, Newspaper, Radio, Repeat, Search, ShieldAlert, SlidersHorizontal, TriangleAlert, X } from 'lucide-react';
import type { Category, EvidenceStatus, ReviewStatus, ScoreBand, TopicFilters, TopicSummary } from '../../lib/api/types';
import { useRules, useTopics } from '../../lib/hooks';
import { BAND_LABEL, CATEGORY_LABEL, EVIDENCE_LABEL, REVIEW_LABEL } from '../../lib/labels';
import { fmtDateTime, scoreText } from '../../lib/format';
import { useDisclosureMotion, useEntrance, useRevealNew } from '../../lib/useMotion';
import { useApp } from '../context';
import { BandPill, Button, ErrorBox, EvidencePill, Loading, Notice, Pill, ReviewPill, inputCls } from '../ui';
import { ScoreBreakdown, ScoreStack } from '../ScoreBreakdown';
import { Disclosure, Select, Tooltip, type SelectOption } from '../ui/controls';
import { SESSION_GATE } from '../../lib/session';

function FilterSelect<T extends string>({
  id,
  testId,
  label,
  value,
  onChange,
  options,
  counts,
}: {
  id: string;
  testId: string;
  label: string;
  value: T | '';
  onChange: (v: T | '') => void;
  options: [T, string][];
  counts?: Record<string, number>;
}) {
  const items: SelectOption<T | ''>[] = [
    { value: '', label: 'Todos' },
    ...options.map(([v, l]) => ({ value: v as T | '', label: `${l}${counts && counts[v] !== undefined ? ` (${counts[v]})` : ''}` })),
  ];
  return (
    <div className="min-w-0">
      <label id={`${id}-label`} htmlFor={id} className="mb-1 block text-xs font-semibold text-ink-2" onClick={() => document.getElementById(id)?.focus()}>
        {label}
      </label>
      <Select id={id} testId={testId} value={value} onChange={onChange} options={items} />
    </div>
  );
}

export function TopicFlags({ t }: { t: TopicSummary }) {
  return (
    <>
      {t.outOfScope && <Pill tone="warn">Fuera de las seis categorías del reto</Pill>}
      {t.possibleSponsored && <Pill tone="warn">Posible contenido patrocinado</Pill>}
      {t.needsInvestigation && (
        <Pill tone="amber" icon={ShieldAlert} testId="topic-needs-investigation">
          Requiere investigación: no habilita publicación
        </Pill>
      )}
      {t.headlineOnly && (
        <Pill tone="neutral" icon={Newspaper} testId="headline-only-notice">
          basado únicamente en titular/metadatos
        </Pill>
      )}
      {t.isRecirculation && (
        <Pill tone="warn" icon={Repeat} testId="recirculation-notice">
          Recirculación de nota antigua
        </Pill>
      )}
      {t.hasContradictions && (
        <Pill tone="bad" icon={GitCompare}>
          Versiones contradictorias
        </Pill>
      )}
      {t.tvnGap && (
        <Pill tone="info" icon={Radio} testId="tvn-gap" title="Dos o más procedencias independientes lo reportan y ninguna nota es de TVN (tvn-2.com).">
          Oportunidad: otros medios lo reportan, TVN no
        </Pill>
      )}
      {t.hasSuspiciousSource && (
        <Pill tone="bad" icon={TriangleAlert}>
          Fuente no confiable
        </Pill>
      )}
    </>
  );
}

const LANG_NAME: Record<string, string> = { en: 'inglés', de: 'alemán', zh: 'chino', ko: 'coreano', fr: 'francés', pt: 'portugués' };

/** Lenguaje de redacción: repetición no es corroboración (CU-03). */
function fuentesReales(t: TopicSummary): string {
  const n = t.independentProvenances, m = t.articleCount;
  const fuentes = `${n} fuente${n === 1 ? '' : 's'} real${n === 1 ? '' : 'es'}`;
  return m > n ? `Ojo: ${m} notas, pero solo ${fuentes}: las réplicas no son corroboración.` : `${fuentes} independiente${n === 1 ? '' : 's'}.`;
}

function TopicCard({ t, onOpen }: { t: TopicSummary; onOpen: (id: string) => void }) {
  const { go } = useApp();
  return (
    <li
      data-testid="topic-card"
      data-topic-id={t.id}
      data-band={t.band}
      data-evidence={t.evidenceStatus}
      data-rank={t.rank ?? undefined}
      data-motion="card"
      data-motion-id={t.id}
      className="comic-panel topic-panel"
    >
      <div data-testid={t.rank ? `topic-card-${t.rank}` : undefined} className="topic-panel-content">
        <div className="topic-rank">
          <span aria-label={`Posición ${t.rank ?? '–'}`}>
            {t.rank ?? '–'}
          </span>
        </div>
        <div className="topic-copy space-y-1.5">
          <p className="kicker">
            {CATEGORY_LABEL[t.category] ?? t.categoryLabel}
            {t.titleLanguage && t.titleLanguage !== 'es' && (
              <span className="ml-2 align-middle normal-case tracking-normal">
                <Pill tone="info" testId="title-language" title="Ningún medio del grupo lo publicó en español. Se muestra el titular original; la cita conserva el texto exacto.">
                  Titular en {LANG_NAME[t.titleLanguage] ?? t.titleLanguage}
                </Pill>
              </span>
            )}
          </p>
          <h3 className="font-display leading-snug">
            <a
              href={`#/ficha/${encodeURIComponent(t.id)}`}
              className="underline-offset-4 hover:text-amber-700 hover:underline"
              data-testid="open-ficha"
              onClick={(e) => {
                e.preventDefault();
                onOpen(t.id);
              }}
            >
              {t.title}
            </a>
          </h3>
          <p className="text-sm text-ink-2">
            <span className="font-semibold text-ink">Por qué: </span>
            {t.topReason}.{' '}
            {SESSION_GATE && <span className="font-semibold text-ink" data-testid="topic-real-sources">{fuentesReales(t)}</span>}
          </p>
          <div className="flex flex-wrap gap-1.5">
            <EvidencePill status={t.evidenceStatus} />
            <ReviewPill status={t.reviewStatus} testId="topic-review-status" />
            <TopicFlags t={t} />
          </div>
          <p className="text-xs text-ink-3">
            {t.articleCount} noticia{t.articleCount === 1 ? '' : 's'} · {t.independentProvenances} procedencia
            {t.independentProvenances === 1 ? '' : 's'} independiente{t.independentProvenances === 1 ? '' : 's'} · última publicación:{' '}
            {fmtDateTime(t.lastPublishedAt)}
          </p>
        </div>
        <div className="topic-score-box">
          <div className="mb-1.5 flex items-baseline justify-between gap-2">
            <p className="flex items-baseline gap-1">
              <Tooltip content="Puntaje de atención 0–100: ordena dónde mirar primero; no prueba verdad ni habilita publicación.">
                <span data-testid="topic-score" className="tabular-nums">
                  {scoreText(t)}
                </span>
              </Tooltip>
              <span className="text-xs text-ink-3">/ 100</span>
            </p>
            <BandPill band={t.band} />
          </div>
          <ScoreStack components={t.scoreComponents} />
          <Disclosure summary="Ver cómo se calculó" className="text-xs" testId="card-score-detail">
            <div className="space-y-2 pt-1">
              <ScoreBreakdown components={t.scoreComponents} variant="compact" testIdPrefix="card-score" />
              <p data-testid="topic-relevance-detail">Pertinencia geográfica: {t.relevanceReason}</p>
            </div>
          </Disclosure>
          <div className="mt-1 grid grid-cols-2 gap-1.5">
            <Button icon={FileSearch} onClick={() => onOpen(t.id)} className="btn-compact">
              Ficha
            </Button>
            <Button icon={ArrowRight} onClick={() => go({ view: 'borradores', topicId: t.id })} className="btn-compact">
              Borradores
            </Button>
          </div>
        </div>
      </div>
    </li>
  );
}

export function Agenda() {
  const { go } = useApp();
  const uid = useId();
  const [q, setQ] = useState('');
  const [debounced, setDebounced] = useState('');
  const [category, setCategory] = useState<Category | ''>('');
  const [evidence, setEvidence] = useState<EvidenceStatus | ''>('');
  const [band, setBand] = useState<ScoreBand | ''>('');
  const [reviewStatus, setReviewStatus] = useState<ReviewStatus | ''>('');
  const [limit, setLimit] = useState(5);
  const [scope, setScope] = useState<'in_scope' | 'all'>('in_scope');
  const [tvnGap, setTvnGap] = useState(false);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const rules = useRules();
  const rootRef = useRef<HTMLDivElement>(null);
  const filtersRef = useDisclosureMotion<HTMLDivElement>(filtersOpen);

  useEffect(() => {
    const t = setTimeout(() => setDebounced(q), 250);
    return () => clearTimeout(t);
  }, [q]);

  const filters: TopicFilters = { q: debounced, category, evidence, band, reviewStatus, limit, scope, tvnGap };
  const { data, error, isLoading, isFetching, refetch } = useTopics(filters);
  const hasFilters = Boolean(category || evidence || band || reviewStatus || debounced || scope === 'all' || tvnGap);
  const facets = data?.facets ?? {};
  const activeFilters = [category, evidence, band, reviewStatus].filter(Boolean).length + (scope === 'all' ? 1 : 0);

  // El encabezado entra al abrir la vista y las tarjetas cuando llegan los datos. Buscar, filtrar o refrescar
  // no repiten nada; «Ver más» anima solo las tarjetas nuevas.
  useEntrance(rootRef, 'agenda', Boolean(data));
  const revealMore = useRevealNew(
    rootRef,
    data?.items.map((t) => t.id) ?? [],
    [debounced, category, evidence, band, reviewStatus, scope, tvnGap].join('|'),
  );

  return (
    <div ref={rootRef} data-testid="agenda-view" className="space-y-3">
      <header data-motion="heading" className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 border-b-2 border-ink pb-1.5">
        <h1 className="font-display text-xl leading-tight sm:text-2xl">Los cinco temas que merecen revisión hoy</h1>
        <Tooltip content="El puntaje ordena dónde mirar primero. No dice qué es verdad: el estado de evidencia es independiente y la decisión editorial es siempre de una persona.">
          <span className="text-xs text-ink-2">
            <strong className="font-mono">{rules.data?.formula ?? 'P = 30R + 25I + 20U + 15N + 10E'}</strong> · {rules.data?.rulesVersion ?? 'scoring-v1'}
          </span>
        </Tooltip>
      </header>

      <form noValidate role="search" aria-label="Filtros de la agenda" className="comic-filters agenda-filters space-y-3 p-2" onSubmit={(e) => e.preventDefault()}>
        <div className="flex items-center gap-2">
          <label htmlFor={`${uid}-q`} className="sr-only">
            Buscar en los temas
          </label>
          <div className="relative min-w-0 flex-1">
            <Search size={16} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-ink-3" aria-hidden="true" />
            <input
              id={`${uid}-q`}
              data-testid="agenda-search"
              type="text"
              role="searchbox"
              autoComplete="off"
              enterKeyHint="search"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Canal, turismo, tarifas…"
              className={`${inputCls} pl-9 pr-11`}
            />
            {q && (
              <button type="button" className="search-clear" aria-label="Borrar búsqueda" data-testid="agenda-search-clear" onClick={() => setQ('')}>
                <X size={16} aria-hidden="true" />
              </button>
            )}
          </div>

        <Button
          className="shrink-0"
          aria-pressed={tvnGap}
          variant={tvnGap ? 'primary' : 'secondary'}
          icon={Radio}
          onClick={() => {
            setTvnGap(!tvnGap);
            setLimit(5);
          }}
          data-testid="filter-tvn-gap"
          title="Temas que otros medios reportan (≥ 2 procedencias independientes) y TVN todavía no"
        >
          <span className="hidden sm:inline">TVN aún no lo cubre</span>
          <span className="sm:hidden">Sin TVN</span>
        </Button>
        <Button
          className="shrink-0 justify-between"
          aria-expanded={filtersOpen}
          aria-controls={`${uid}-filters`}
          onClick={() => setFiltersOpen(!filtersOpen)}
          data-testid="filters-toggle"
        >
          <span className="inline-flex items-center gap-2">
            <SlidersHorizontal size={16} aria-hidden="true" />
            Filtros{activeFilters > 0 ? ` (${activeFilters} activo${activeFilters === 1 ? '' : 's'})` : ''}
          </span>
          <ChevronDown size={16} aria-hidden="true" className={`comic-chevron ${filtersOpen ? 'rotate-180' : ''}`} />
        </Button>
        </div>

        <div id={`${uid}-filters`} ref={filtersRef} className={`${filtersOpen ? 'grid' : 'hidden'} grid-cols-1 gap-3 min-[480px]:grid-cols-2 md:grid-cols-3`}>
          <div className="min-w-0">
            <label id={`${uid}-scope-label`} htmlFor={`${uid}-scope`} className="mb-1 block text-xs font-semibold text-ink-2" onClick={() => document.getElementById(`${uid}-scope`)?.focus()}>
              Alcance temático
            </label>
            <Select
              id={`${uid}-scope`}
              testId="filter-scope"
              value={scope}
              onChange={(next) => {
                setScope(next);
                setLimit(5);
              }}
              options={[
                { value: 'in_scope', label: 'Seis categorías del reto' },
                { value: 'all', label: 'Incluir indeterminadas' },
              ]}
            />
          </div>
          <FilterSelect
            id={`${uid}-cat`}
            testId="filter-category"
            label="Categoría"
            value={category}
            onChange={setCategory}
            options={Object.entries(CATEGORY_LABEL) as [Category, string][]}
            counts={facets.category}
          />
          <FilterSelect
            id={`${uid}-ev`}
            testId="filter-evidence"
            label="Estado de evidencia"
            value={evidence}
            onChange={setEvidence}
            options={Object.entries(EVIDENCE_LABEL) as [EvidenceStatus, string][]}
            counts={facets.evidence}
          />
          <FilterSelect
            id={`${uid}-band`}
            testId="filter-band"
            label="Prioridad"
            value={band}
            onChange={setBand}
            options={Object.entries(BAND_LABEL) as [ScoreBand, string][]}
            counts={facets.band}
          />
          <FilterSelect
            id={`${uid}-rev`}
            testId="filter-review"
            label="Revisión"
            value={reviewStatus}
            onChange={setReviewStatus}
            options={Object.entries(REVIEW_LABEL) as [ReviewStatus, string][]}
            counts={facets.reviewStatus}
          />
          <div className="flex items-end">
            <Button
              className="w-full"
              disabled={!hasFilters}
              onClick={() => {
                setQ('');
                setCategory('');
                setEvidence('');
                setBand('');
                setReviewStatus('');
                setScope('in_scope');
                setTvnGap(false);
              }}
              data-testid="filters-clear"
            >
              Limpiar filtros
            </Button>
          </div>
        </div>
      </form>

      {isLoading && <Loading label="Cargando agenda…" />}
      {error && <ErrorBox error={error} onRetry={() => refetch()} />}

      {data && (
        <div aria-live="polite" aria-busy={isFetching}>
          <p className="mb-2 text-xs text-ink-3">
            <span data-testid="agenda-count">
              {data.items.length === 0
                ? 'Sin resultados'
                : `Mostrando ${data.items.length} de ${data.total} tema${data.total === 1 ? '' : 's'}${hasFilters ? ' con los filtros aplicados' : ''}.`}
            </span>{' '}
            <span data-testid="agenda-scope-note">
              {scope === 'in_scope' ? `${data.outOfScopeCount} temas de categoría indeterminada quedan fuera de esta agenda.` : 'Se incluyen temas fuera de las seis categorías; requieren revisión de su pertinencia.'}
            </span>
          </p>
          {data.items.length === 0 ? (
            <Notice tone="info" title="Ningún tema coincide" testId="agenda-empty">
              Prueba con otra búsqueda o limpia los filtros. El sistema no inventa temas para completar los cinco lugares.
            </Notice>
          ) : (
            <ol data-testid="agenda-list" className="comic-agenda">
              {data.items.map((t) => (
                <TopicCard key={t.id} t={t} onOpen={(id) => go({ view: 'ficha', topicId: id })} />
              ))}
            </ol>
          )}
          {data.total > data.items.length && (
            <div className="mt-3 text-center">
              <Button
                onClick={() => {
                  revealMore();
                  setLimit(Math.min(50, limit + 10));
                }}
                data-testid="agenda-more"
              >
                Ver más temas ({data.total - data.items.length} restantes)
              </Button>
            </div>
          )}
          {limit > 5 && data.total <= data.items.length && (
            <div className="mt-3 text-center">
              <Button variant="ghost" onClick={() => setLimit(5)}>
                Volver a los cinco principales
              </Button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
