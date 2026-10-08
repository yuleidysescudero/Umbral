import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { QueryClient, QueryClientProvider, useQueryClient } from '@tanstack/react-query';
import { ChevronDown, Clock, Database, FileSearch, FlaskConical, ListOrdered, LogOut, Moon, MoreHorizontal, PenLine, Sun, Tags, TriangleAlert, Users, WifiOff } from 'lucide-react';
import type { BootProgress, UmbralApi } from '../lib/api/client';
import { resolveApi } from '../lib/api';
import { initAuth, type AuthState } from '../lib/auth';
import { useRoute, type Route } from '../lib/router';
import { readLocal, writeLocal } from '../lib/storage';
import { useHealth, useRules } from '../lib/hooks';
import { DATA_MODE_LABEL } from '../lib/labels';
import { installInteractions } from '../lib/interactions';
import { useDisclosureMotion } from '../lib/useMotion';
import { fmtDateTime } from '../lib/format';
import { AppContext, useApp } from './context';
import { Agenda } from './views/Agenda';
import { Ficha } from './views/Ficha';
import { Drafts } from './views/Drafts';
import { Sources } from './views/Sources';
import { Mesa } from './views/Mesa';
import { Etiquetar } from './views/Etiquetar';
import { SessionGate } from './SessionGate';
import { guardarSesion, leerSesion, puedeEtiquetar, ROLES, SESSION_GATE, type Session } from '../lib/session';
import { applyTheme, readTheme, type Theme } from '../lib/theme';
import { MiniIA } from './mascot/MiniIA';
import { TvnLogo } from './brand/TvnLogo';
import { Assistant } from './Assistant';
import { ErrorBox, Notice, Pill } from './ui';

export const DISCLAIMER = 'Prototipo de hackIAthon para TVN Media. No es un producto oficial de Televisora Nacional, S.A.';

const NAV: NavItem[] = [
  { view: 'agenda', label: 'Agenda', short: 'Agenda', icon: ListOrdered, testId: 'nav-agenda' },
  { view: 'ficha', label: 'Ficha', short: 'Ficha', icon: FileSearch, testId: 'nav-ficha' },
  { view: 'borradores', label: 'Borradores', short: 'Borradores', icon: PenLine, testId: 'nav-borradores' },
  { view: 'fuentes', label: 'Fuentes y evaluación', short: 'Fuentes', icon: Database, testId: 'nav-fuentes' },
];
const NAV_EXTRA: NavItem[] = [
  { view: 'mesa', label: 'Mesa', short: 'Mesa', icon: Users, testId: 'nav-mesa' },
  { view: 'etiquetar', label: 'Etiquetar', short: 'Etiquetar', icon: Tags, testId: 'nav-etiquetar' },
];

function SessionChip() {
  const { session, salir } = useApp();
  if (!SESSION_GATE || !session) return null;
  return (
    <span className="tvn-role" data-testid="session-chip">
      <span className="tvn-role-label whitespace-nowrap" data-mode={session.modo}>{ROLES[session.rol].nombre}{session.modo === 'compartido' ? ' · equipo' : ' · local'}</span>
      <button type="button" onClick={salir} aria-label="Cambiar de rol">
        <LogOut size={14} aria-hidden="true" /><span className="tvn-role-label">Cambiar</span>
      </button>
    </span>
  );
}

function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(() => readTheme());
  useEffect(() => applyTheme(theme), [theme]);
  const dark = theme === 'dark';
  return (
    <button
      type="button"
      className="tvn-icon-btn"
      aria-pressed={dark}
      aria-label={dark ? 'Modo oscuro activado: cambiar a claro' : 'Activar modo oscuro'}
      data-testid="theme-toggle"
      onClick={() => setTheme(dark ? 'light' : 'dark')}
    >
      {dark ? <Sun size={18} aria-hidden="true" /> : <Moon size={18} aria-hidden="true" />}
    </button>
  );
}

function StatusItem({ label, children, testId }: { label: string; children: ReactNode; testId?: string }) {
  return (
    <div className="min-w-0 sm:flex sm:items-baseline sm:gap-1" data-testid={testId}>
      <dt className="text-ink-3">{label}</dt>
      <dd className="font-semibold">{children}</dd>
    </div>
  );
}

const fmtCut = new Intl.DateTimeFormat('es-PA', { timeZone: 'America/Panama', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit', hour12: false });

/** Estado del snapshot en UNA línea colapsable; los avisos largos pasan a chips con globo de ayuda. */
function StatusBar() {
  const { api, mockReason, authMode } = useApp();
  const { data: h, error } = useHealth();
  const rules = useRules();
  const [statusOpen, setStatusOpen] = useState(false);
  const detailsRef = useDisclosureMotion<HTMLDListElement>(statusOpen);
  const stale = h ? Date.now() - Date.parse(h.cutoffUtc) > 36 * 60 * 60 * 1000 : false;
  return (
    <div className="space-y-2" data-testid="status-bar">
      {api.kind === 'mock' && (
        <Notice tone="amber" icon={FlaskConical} title="MODO DEMOSTRACIÓN del frontend: datos simulados, no son noticias ni cifras reales" testId="mock-banner" role="status">
          {mockReason} Para usar la API real, arranca el backend (puerto 8000) y define <code className="font-mono">PUBLIC_API_MODE=live</code>.
        </Notice>
      )}
      {error && api.kind === 'live' && (
        <div data-testid="api-down">
          <ErrorBox error={error} />
        </div>
      )}
      {h && (
        <div className="snapshot-line" data-testid="snapshot-line">
          <Pill tone={h.dataMode === 'congelado' ? 'ok' : 'warn'} testId="data-mode-banner" data-mode={h.dataMode}>
            {DATA_MODE_LABEL[h.dataMode]}
            {h.provisional && h.dataMode !== 'provisional' ? ' · provisional' : ''}
          </Pill>
          <span data-testid="snapshot-cutoff">corte {fmtCut.format(new Date(h.cutoffUtc))}</span>
          <span aria-hidden="true">·</span>
          <span>reglas <span data-testid="rules-version" className="font-mono font-semibold">{rules.data?.rulesVersion ?? h.rulesVersion}</span></span>
          {h.offline && (
            <Pill tone="info" icon={WifiOff} testId="offline-indicator">
              Sin conexión: llamadas externas bloqueadas
            </Pill>
          )}
          {h.classifier === 'laya' && (
            <span data-testid="classification-limit">
              <Pill tone="warn" icon={TriangleAlert} title="Laya clasifica automáticamente sin calibración validada: puede asignar categorías erróneas y sus porcentajes no son confianza editorial. Revisa categoría e impacto antes de usar el ranking.">
                Clasificación sin calibrar
              </Pill>
            </span>
          )}
          {stale && (
            <span data-testid="stale-snapshot">
              <Pill tone="warn" icon={Clock} title="El corte tiene más de 36 horas. Los datos siguen siendo el último corte válido: revisa las fechas de las fuentes antes de usarlos.">
                Corte de hace más de 36 h
              </Pill>
            </span>
          )}
          <button
            type="button"
            className="inline-flex min-h-9 items-center gap-1 rounded-full px-2 font-semibold text-info underline underline-offset-2"
            aria-expanded={statusOpen}
            aria-controls="status-details"
            onClick={() => setStatusOpen(!statusOpen)}
            data-testid="status-toggle"
          >
            {statusOpen ? 'ocultar detalles' : 'ver detalles'}
            <ChevronDown size={14} aria-hidden="true" className={`comic-chevron shrink-0 ${statusOpen ? 'rotate-180' : ''}`} />
          </button>
        </div>
      )}
      {h && (
        <dl id="status-details" ref={detailsRef} className={`comic-statusbar ${statusOpen ? 'grid sm:flex' : 'hidden'} grid-cols-2 gap-x-4 gap-y-2 rounded-md border border-rule bg-card px-3 py-2 text-xs sm:flex-wrap sm:items-center sm:gap-x-5`} aria-label="Estado de los datos">
          <StatusItem label="Snapshot">
            <span data-testid="snapshot-badge" className="font-mono [overflow-wrap:anywhere]">
              {h.snapshotId}
            </span>
          </StatusItem>
          <StatusItem label="Corte">{fmtDateTime(h.cutoffUtc)}</StatusItem>
          <StatusItem label="Clasificador">{h.classifier ?? 'sin clasificador'}</StatusItem>
          <StatusItem label="Acceso">
            {authMode === 'public' ? 'Público · trabajo guardado en este navegador' : (authMode === 'firebase-anonymous' ? 'Sesión anónima (Firebase)' : 'Usuario único local') + ' · ' + h.persistence}
          </StatusItem>
        </dl>
      )}
      {h && (h.containsFixtures || h.dataMode === 'fixture') && (
        <Notice tone="warn" title="Este snapshot contiene datos de fixture" testId="fixture-notice">
          Sirven para probar el recorrido; no representan noticias ni indicadores reales. Se muestran etiquetados como tales.
        </Notice>
      )}
      {h && h.integrity.errors.length > 0 && (
        <Notice tone="bad" title="Falló la verificación de integridad del snapshot" testId="integrity-errors" role="alert">
          {h.integrity.errors.join(' · ')}
        </Notice>
      )}
    </div>
  );
}

type NavItem = { view: Route['view']; label: string; short: string; icon: typeof ListOrdered; testId: string };

/** Cuántos ítems caben en línea: por debajo de 1360 px como máximo cuatro, y nunca más de los que caben medidos. */
function useNavFit(items: NavItem[], wide: boolean) {
  const navRef = useRef<HTMLDivElement>(null);
  const measureRef = useRef<HTMLDivElement>(null);
  const [fit, setFit] = useState(items.length);
  useLayoutEffect(() => {
    const nav = navRef.current;
    const measure = measureRef.current;
    if (!nav || !measure) return;
    const compute = () => {
      const widths = Array.from(measure.children).map((el) => (el as HTMLElement).getBoundingClientRect().width);
      const gap = 4;
      const more = 96;
      const room = nav.getBoundingClientRect().width;
      const cap = wide ? items.length : Math.min(4, items.length);
      let used = 0;
      let n = 0;
      for (let i = 0; i < Math.min(cap, widths.length); i++) {
        const rest = i + 1 < items.length ? more + gap : 0;
        if (used + widths[i]! + rest > room) break;
        used += widths[i]! + gap;
        n++;
      }
      setFit(Math.max(1, n));
    };
    compute();
    const ro = new ResizeObserver(compute);
    ro.observe(nav);
    return () => ro.disconnect();
  }, [items, wide]);
  return { navRef, measureRef, fit };
}

function MoreMenu({ items, onGo, activeView }: { items: NavItem[]; onGo: (v: Route['view']) => void; activeView: Route['view'] }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent ? e.key === 'Escape' : !ref.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', close);
    document.addEventListener('keydown', close);
    return () => {
      document.removeEventListener('mousedown', close);
      document.removeEventListener('keydown', close);
    };
  }, [open]);
  const activeInside = items.some((i) => i.view === activeView);
  return (
    <div className="tvn-more" ref={ref}>
      <button
        type="button"
        className="tvn-nav-link"
        aria-haspopup="true"
        aria-expanded={open}
        aria-current={activeInside ? 'page' : undefined}
        data-testid="nav-more"
        onClick={() => setOpen(!open)}
      >
        <MoreHorizontal size={16} aria-hidden="true" />
        Más
      </button>
      {open && (
        <div className="tvn-more-menu" role="menu" data-testid="nav-more-menu">
          {items.map(({ view, label, icon: Ico, testId }) => (
            <a
              key={view}
              role="menuitem"
              href={`#/${view}`}
              data-testid={testId}
              aria-current={activeView === view ? 'page' : undefined}
              onClick={(e) => {
                e.preventDefault();
                setOpen(false);
                onGo(view);
              }}
            >
              <Ico size={16} aria-hidden="true" />
              {label}
            </a>
          ))}
        </div>
      )}
    </div>
  );
}

function Shell({ assistantOpen, setAssistantOpen, seed }: { assistantOpen: boolean; setAssistantOpen: (v: boolean) => void; seed: { text: string; n: number } }) {
  const { route, go, session } = useApp();
  const [mobile, setMobile] = useState(false); // panel del asistente como diálogo (< 1024 px)
  const [phone, setPhone] = useState(false); // barra inferior (≤ 768 px)
  const [wide, setWide] = useState(true); // ≥ 1360 px: toda la navegación en línea
  const mainRef = useRef<HTMLElement>(null);
  const lastTopic = useRef<string | null>(null);
  if ('topicId' in route && route.topicId) lastTopic.current = route.topicId;

  // Respuesta táctil global (pulsación, trazos y detalles); se retira al desmontar la aplicación.
  useEffect(() => installInteractions(), []);

  useEffect(() => {
    const queries: [string, (v: boolean) => void][] = [
      ['(max-width: 1023px)', setMobile],
      ['(max-width: 768px)', setPhone],
      ['(min-width: 1360px)', setWide],
    ];
    const offs = queries.map(([q, set]) => {
      const media = window.matchMedia(q);
      const update = () => set(media.matches);
      update();
      media.addEventListener('change', update);
      return () => media.removeEventListener('change', update);
    });
    return () => offs.forEach((off) => off());
  }, []);

  // Mover el foco al contenido principal al cambiar de vista (accesibilidad de SPA).
  useEffect(() => {
    mainRef.current?.focus({ preventScroll: true });
    window.scrollTo({ top: 0 });
  }, [route.view]);

  const items = useMemo(
    () => (SESSION_GATE ? [...NAV, ...NAV_EXTRA.filter((n) => n.view !== 'etiquetar' || puedeEtiquetar(session ?? null))] : NAV),
    [session],
  );
  const { navRef, measureRef, fit } = useNavFit(items, wide && !assistantOpen);
  const goView = (view: Route['view']) =>
    go(view === 'agenda' || view === 'fuentes' || view === 'mesa' || view === 'etiquetar' ? { view } : { view, topicId: lastTopic.current });
  const link = ({ view, label, short, icon: Ico, testId }: NavItem, variant: 'top' | 'bottom') => (
    <a
      key={view}
      href={`#/${view}`}
      data-testid={testId}
      aria-current={route.view === view ? 'page' : undefined}
      onClick={(e) => {
        e.preventDefault();
        goView(view);
      }}
      className={variant === 'top' ? 'tvn-nav-link' : undefined}
    >
      <Ico size={variant === 'top' ? 16 : 20} aria-hidden="true" />
      {variant === 'top' ? label : short}
    </a>
  );

  return (
    <div data-testid="app-root" className={assistantOpen ? 'lg:pr-[26rem]' : ''}>
      <a href="#contenido" inert={assistantOpen && mobile} className="skip-link">
        Saltar al contenido
      </a>
      <header inert={assistantOpen && mobile} className="tvn-masthead sticky top-0 z-30 no-print" data-testid="masthead">
        <div className="tvn-masthead-grid mx-auto max-w-[90rem] px-4 py-2">
          <a href="/" className="tvn-brand" aria-label="Umbral × TVN, inicio" data-testid="brand">
            <TvnLogo size={38} />
            <span className="tvn-brand-divider" aria-hidden="true" />
            <span>
              <span className="tvn-brand-name">Umbral</span>
              <span className="tvn-brand-sub">Agenda editorial</span>
            </span>
          </a>
          {!phone ? (
            <nav aria-label="Vistas principales" className="tvn-nav" ref={navRef} data-testid="main-nav">
              {items.slice(0, fit).map((it) => link(it, 'top'))}
              {fit < items.length && <MoreMenu items={items.slice(fit)} onGo={goView} activeView={route.view} />}
              <div ref={measureRef} aria-hidden="true" className="pointer-events-none invisible absolute left-0 top-0 flex gap-1">
                {items.map(({ view, label, icon: Ico }) => (
                  <span key={view} className="tvn-nav-link">
                    <Ico size={16} />
                    {label}
                  </span>
                ))}
              </div>
            </nav>
          ) : null}
          <div className="tvn-actions">
            <SessionChip />
            <ThemeToggle />
            <button
              type="button"
              className="tvn-assistant-btn"
              onClick={() => setAssistantOpen(!assistantOpen)}
              aria-expanded={assistantOpen}
              aria-controls="assistant-panel"
              data-testid="assistant-toggle"
              aria-label="Asistente"
            >
              <span className="tvn-assistant-face">
                <MiniIA size={28} state={assistantOpen ? 'escuchando' : 'idle'} />
              </span>
              <span className="tvn-assistant-label">Asistente</span>
            </button>
          </div>
        </div>
      </header>
      {phone && (
        <nav aria-label="Vistas principales" className="tvn-tabbar no-print" inert={assistantOpen && mobile} data-testid="bottom-nav">
          {items.map((it) => link(it, 'bottom'))}
        </nav>
      )}

      <main id="contenido" inert={assistantOpen && mobile} ref={mainRef} tabIndex={-1} className="comic-sheet mx-auto max-w-6xl space-y-3 px-4 pb-28 pt-4 outline-none md:pb-14">
        <StatusBar />
        <div key={route.view} className="pt-1">
          {route.view === 'agenda' && <Agenda />}
          {route.view === 'ficha' && <Ficha />}
          {route.view === 'borradores' && <Drafts />}
          {route.view === 'fuentes' && <Sources />}
          {route.view === 'mesa' && <Mesa />}
          {route.view === 'etiquetar' && (puedeEtiquetar(session ?? null) || !SESSION_GATE ? <Etiquetar /> : (
            <Notice tone="info" title="El rol Jurado no etiqueta" testId="etiquetar-bloqueado">
              Para que las métricas humanas no se contaminen, solo los roles editoriales etiquetan. Puedes revisar los resultados en «Fuentes y evaluación».
            </Notice>
          ))}
        </div>
        <footer className="mt-8 border-t border-rule pt-3 text-xs text-ink-3">
          Umbral prioriza la atención editorial y prepara borradores para revisión humana. No publica, no etiqueta noticias como verdaderas o falsas y no sustituye el criterio del equipo.
        </footer>
      </main>
      <p className="tvn-disclaimer no-print" data-testid="tvn-disclaimer">{DISCLAIMER}</p>
      <Assistant open={assistantOpen} modal={mobile} onClose={() => setAssistantOpen(false)} seed={seed} />
    </div>
  );
}

type Boot = { api: UmbralApi; reason: string | null; auth: AuthState };

function Inner() {
  const queryClient = useQueryClient();
  const [bootAttempt, setBootAttempt] = useState(0);
  const [progress, setProgress] = useState<BootProgress | null>(null);
  const [boot, setBoot] = useState<Boot | null>(null);
  const [bootError, setBootError] = useState<string | null>(null);
  const [route, go] = useRoute();
  const [reviewer, setReviewerState] = useState(() => readLocal('umbral.reviewer', ''));
  const [session, setSession] = useState<Session | null>(() => (SESSION_GATE ? leerSesion() : null));
  const [assistantOpen, setAssistantOpen] = useState(false);
  const [seed, setSeed] = useState({ text: '', n: 0 });

  useEffect(() => {
    let live = true;
    const controller = new AbortController();
    let activeApi: UmbralApi | null = null;
    setBootError(null);
    setProgress(null);
    (async () => {
      try {
        const auth = await initAuth();
        if (auth.error) throw new Error(auth.error);
        const r = await resolveApi((next) => { if (live) setProgress(next); }, controller.signal); activeApi = r.api;
        if (live) setBoot({ api: r.api, reason: r.reason, auth }); else await r.api.close?.();
      } catch (e) {
        if (live) setBootError(e instanceof Error ? e.message : 'Error de arranque');
      }
    })();
    return () => {
      live = false;
      controller.abort();
      void activeApi?.close?.();
    };
  }, [bootAttempt]);

  useEffect(() => boot?.api.subscribe?.(() => { void Promise.all(['topics','topic','rules','workspace-cases'].map((key) => queryClient.invalidateQueries({ queryKey: [key] }))); }), [boot, queryClient]);

  const setReviewer = useCallback((name: string) => {
    setReviewerState(name);
    writeLocal('umbral.reviewer', name);
  }, []);
  const salir = useCallback(() => { guardarSesion(null); setSession(null); }, []);
  const onEnter = useCallback((s: Session) => { setSession(s); setReviewer(s.nombre); }, [setReviewer]);
  const openAssistant = useCallback((prompt?: string) => {
    setAssistantOpen(true);
    if (prompt) setSeed((s) => ({ text: prompt, n: s.n + 1 }));
  }, []);

  const ctx = useMemo(
    () =>
      boot
        ? {
            api: boot.api,
            mockReason: boot.reason,
            route,
            go,
            reviewer,
            setReviewer,
            openAssistant,
            authMode: boot.auth.mode,
            session,
            salir,
          }
        : null,
    [boot, route, go, reviewer, setReviewer, openAssistant, session, salir],
  );

  if (SESSION_GATE && !session) return <SessionGate onEnter={onEnter} />;
  if (bootError) return <div className="mx-auto max-w-xl p-6" data-testid="app-boot-error"><ErrorBox error={new Error(bootError)} onRetry={() => setBootAttempt((value) => value + 1)} /></div>;
  if (!ctx) return (
    <div className="mx-auto flex max-w-xl flex-col items-center gap-4 p-8 text-center" data-testid="app-loading">
      <MiniIA size={120} state="pensando" testId="boot-mascot" />
      <p role="status" className="mascot-bubble">{progress?.message ?? 'Un momentito, estoy preparando la agenda…'}</p>
      {progress && <p className="text-sm text-ink-3" aria-live="polite">Intento {progress.attempt} · {Math.floor(progress.elapsedMs / 1000)} s. El primer inicio puede tardar hasta 90 segundos.</p>}
      <p className="text-xs text-ink-3">{DISCLAIMER}</p>
    </div>
  );
  return (
    <AppContext.Provider value={ctx}>
      <Shell assistantOpen={assistantOpen} setAssistantOpen={setAssistantOpen} seed={seed} />
    </AppContext.Provider>
  );
}

export default function App() {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: { queries: { staleTime: 15_000, refetchOnWindowFocus: false, retry: 1 } },
      }),
  );
  return (
    <QueryClientProvider client={client}>
      <Inner />
    </QueryClientProvider>
  );
}
