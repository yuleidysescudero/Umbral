// Mesa compartida: copia de cada decisión de revisión para que todo el equipo la vea (Supabase, solo inserción).
// La revisión validada sigue guardándose en el IndexedDB de este navegador; esto solo la comparte.
import type { ReviewStatus } from './api/types';
import { SUPABASE, tokenVigente, type Session } from './session';

export const ESTADO_MESA: Record<ReviewStatus, string> = {
  nuevo: 'nuevo',
  en_revision: 'en revisión',
  requiere_evidencia: 'requiere evidencia',
  aprobado_como_borrador: 'aprobado como borrador',
  descartado: 'descartado',
};
const DESDE_MESA = Object.fromEntries(Object.entries(ESTADO_MESA).map(([k, v]) => [v, k])) as Record<string, ReviewStatus>;

export type Decision = {
  id: number;
  id_evento: string;
  titulo: string | null;
  estado: ReviewStatus;
  persona: string;
  rol: string | null;
  nota: string;
  created_at: string;
};

function cabeceras(s: Session): Record<string, string> {
  return { apikey: SUPABASE.anon, Authorization: `Bearer ${s.token}`, 'Content-Type': 'application/json' };
}

export async function compartirDecision(sesion: Session, topicId: string, titulo: string, estado: ReviewStatus, nota: string | null): Promise<boolean> {
  const s = await tokenVigente(sesion);
  if (!s) return false;
  try {
    const fila = { id_evento: topicId, titulo, estado: ESTADO_MESA[estado], persona: s.nombre, rol: s.rol, nota: nota ?? '',
      reglas: 'scoring-v1', producto: 'umbral', usuario_id: s.userId };
    const r = await fetch(`${SUPABASE.url}/rest/v1/revisiones`, { method: 'POST', headers: cabeceras(s), body: JSON.stringify(fila) });
    if (!r.ok) return false;
    await fetch(`${SUPABASE.url}/rest/v1/bitacora`, { method: 'POST', headers: cabeceras(s), body: JSON.stringify({
      accion: 'revision', detalle: { id_evento: topicId, estado: fila.estado, nota: fila.nota }, persona: s.nombre, rol: s.rol,
      producto: 'umbral', usuario_id: s.userId }) });
    return true;
  } catch {
    return false;
  }
}

export async function leerMesa(sesion: Session): Promise<Decision[] | null> {
  const s = await tokenVigente(sesion);
  if (!s) return null;
  const r = await fetch(`${SUPABASE.url}/rest/v1/revisiones?producto=eq.umbral&select=*&order=created_at.desc&limit=300`, { headers: cabeceras(s) });
  if (!r.ok) throw new Error('No se pudo leer la mesa compartida.');
  const filas = (await r.json()) as (Omit<Decision, 'estado'> & { estado: string })[];
  return filas.map((f) => ({ ...f, estado: DESDE_MESA[f.estado] ?? 'nuevo' }));
}
