// Etiquetado humano a ciegas (eval/labels/LEEME.md): la etiqueta la pone una persona, nunca el sistema.
// Con sesión compartida se guarda en Supabase (solo inserción; gana la más reciente por ítem); sin red, en este navegador.
// scripts/importar_etiquetas_mesa.py vuelca las etiquetas a las hojas CSV que leen los scripts de eval/.
import { readLocal, writeLocal } from './storage';
import { SUPABASE, puedeEtiquetar, tokenVigente, type Session } from './session';

export type TipoEtiqueta = 'tema' | 'par' | 'afirmacion';
export type Etiqueta = { tipo: TipoEtiqueta; item_id: string; valor: string; comentario: string; persona: string; rol?: string; sesion?: string; created_at: string };

const MAX_COMENTARIO = 500;

export type Hojas = {
  snapshotId: string;
  tema: { id: string; texto: string; medio?: string | null }[];
  par: { id: string; a: string; b: string }[];
  afirmacion: { id: string; texto: string; cita: string | null; campo: string | null; titularCitado: string | null; medio: string | null }[];
};

const LOCAL = 'umbral.etiquetas';

function locales(): Etiqueta[] {
  try { return JSON.parse(readLocal(LOCAL, '[]')) as Etiqueta[]; } catch { return []; }
}

export async function cargarHojas(): Promise<Hojas> {
  const r = await fetch('/etiquetado/hojas.json', { cache: 'no-store' });
  if (!r.ok) throw new Error('No se encontraron las hojas de etiquetado de este snapshot.');
  return (await r.json()) as Hojas;
}

export async function listarEtiquetas(sesion: Session | null): Promise<Etiqueta[]> {
  const s = sesion ? await tokenVigente(sesion) : null;
  if (!s) return locales();
  const r = await fetch(`${SUPABASE.url}/rest/v1/etiquetas?producto=eq.umbral&select=*&order=created_at.asc`, {
    headers: { apikey: SUPABASE.anon, Authorization: `Bearer ${s.token}` },
  });
  if (!r.ok) throw new Error('No se pudieron leer las etiquetas del equipo.');
  return (await r.json()) as Etiqueta[];
}

export async function guardarEtiqueta(sesion: Session, tipo: TipoEtiqueta, item_id: string, valor: string, comentario: string): Promise<Etiqueta> {
  if (!puedeEtiquetar(sesion)) throw new Error('El rol Jurado no etiqueta: sus marcas no cuentan para las métricas humanas.');
  comentario = comentario.slice(0, MAX_COMENTARIO);
  const fila: Etiqueta = { tipo, item_id, valor, comentario, persona: sesion.nombre, rol: sesion.rol, sesion: sesion.sesionId, created_at: new Date().toISOString() };
  const s = await tokenVigente(sesion);
  if (s) {
    const base = { tipo, item_id, valor, comentario, persona: s.nombre, producto: 'umbral', usuario_id: s.userId };
    const post = (body: object) => fetch(`${SUPABASE.url}/rest/v1/etiquetas`, {
      method: 'POST',
      headers: { apikey: SUPABASE.anon, Authorization: `Bearer ${s.token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    let r = await post({ ...base, rol: s.rol, sesion: s.sesionId ?? null });
    // Base sin la migración supabase/etiquetas_integridad.sql: se guarda igual (el rol queda en `persona`).
    if (r.status === 400) r = await post(base);
    if (!r.ok) throw new Error('No se pudo guardar la etiqueta en la mesa compartida.');
    return fila;
  }
  writeLocal(LOCAL, JSON.stringify([...locales(), fila]));
  return fila;
}

/** Última etiqueta por ítem (el historial completo se conserva). */
export function vigentes(lista: Etiqueta[]): Map<string, Etiqueta> {
  const m = new Map<string, Etiqueta>();
  for (const e of lista) m.set(`${e.tipo}:${e.item_id}`, e);
  return m;
}
