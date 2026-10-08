export const PANAMA_TZ = 'America/Panama';

const fmtFull = new Intl.DateTimeFormat('es-PA', {
  timeZone: PANAMA_TZ,
  day: 'numeric',
  month: 'short',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
});
const fmtDay = new Intl.DateTimeFormat('es-PA', { timeZone: PANAMA_TZ, day: 'numeric', month: 'short', year: 'numeric' });

/** Fecha/hora UTC (ISO) → texto en hora de Panamá (UTC-5). `null` → «fecha desconocida». */
export function fmtDateTime(iso: string | null | undefined, unknown = 'fecha desconocida'): string {
  if (!iso) return unknown;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return unknown;
  return `${fmtFull.format(d)} (hora de Panamá)`;
}

export function fmtDate(iso: string | null | undefined, unknown = 'fecha desconocida'): string {
  if (!iso) return unknown;
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? unknown : fmtDay.format(d);
}

/** Mismo redondeo que la API (ROUND_HALF_UP sobre el decimal visible, coma decimal): 74,55 → 74,6. */
export function fmtScore(n: number): string {
  const tenths = Math.round(Number((Math.abs(n) * 10).toPrecision(12)));
  return ((Math.sign(n) < 0 ? -tenths : tenths) / 10).toFixed(1).replace('.', ',');
}

/** Puntaje tal como lo entrega la API (`scoreDisplay`); solo si falta, se calcula con el mismo redondeo. */
export function scoreText(t: { score: number; scoreDisplay?: string | null }): string {
  return t.scoreDisplay || fmtScore(t.score);
}

export function fmtNumber(n: number | null | undefined, digits = 2): string {
  if (n === null || n === undefined) return '—';
  return n.toLocaleString('es-PA', { maximumFractionDigits: digits });
}

export function pct(n: number): string {
  return `${Math.round(n * 100)} %`;
}

export function shortHash(h: string | null | undefined, n = 12): string {
  return h ? `${h.slice(0, n)}…` : '—';
}
