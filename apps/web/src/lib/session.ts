// Sesión por rol: se entra tocando un botón, sin escribir contraseña.
// Con Supabase configurado, cada rol usa una cuenta de demostración (solo puede AGREGAR registros); sin Supabase,
// la sesión vive en este navegador y la revisión sigue funcionando sin red (T10).
import { readLocal, writeLocal } from './storage';

export type Rol = 'editor' | 'productor' | 'revisor' | 'jurado';

export const ROLES: Record<Rol, { nombre: string; firma: string; descripcion: string; email: string }> = {
  editor: { nombre: 'Editor/a', firma: 'Mesa editorial', descripcion: 'Agenda priorizada, fichas y decisión editorial', email: 'editor@rastro-demo.com' },
  productor: { nombre: 'Productor/a digital', firma: 'Producción digital', descripcion: 'Titulares, resumen web y copy social', email: 'digital@rastro-demo.com' },
  revisor: { nombre: 'Revisor/a', firma: 'Revisión', descripcion: 'Acepta, corrige o descarta borradores', email: 'revisor@rastro-demo.com' },
  jurado: { nombre: 'Jurado', firma: 'Jurado hackIAthon', descripcion: 'Recorrido completo, métricas y pruebas', email: 'jurado@rastro-demo.com' },
};

export type Session = {
  rol: Rol;
  nombre: string;
  modo: 'compartido' | 'local';
  token?: string;
  userId?: string;
  expira?: number;
};

const env = import.meta.env;
export const SUPABASE = {
  url: String(env.PUBLIC_SUPABASE_URL ?? '').trim().replace(/\/$/, ''),
  anon: String(env.PUBLIC_SUPABASE_ANON_KEY ?? '').trim(),
  demo: String(env.PUBLIC_DEMO_CLAVE ?? '').trim(),
};
export const compartidoDisponible = Boolean(SUPABASE.url && SUPABASE.anon && SUPABASE.demo);

/** Builds con sesión por rol (MEGA en Vercel): entrada sin contraseña, mesa compartida y vista simplificada. */
export const SESSION_GATE = String(env.PUBLIC_SESSION_GATE ?? '').trim() === '1';

const KEY = 'umbral.session';

export function leerSesion(): Session | null {
  try {
    const raw = readLocal(KEY, '');
    return raw ? (JSON.parse(raw) as Session) : null;
  } catch {
    return null;
  }
}

export function guardarSesion(s: Session | null): void {
  writeLocal(KEY, s ? JSON.stringify(s) : '');
}

async function loginDemo(rol: Rol): Promise<Pick<Session, 'token' | 'userId' | 'expira'> | null> {
  if (!compartidoDisponible) return null;
  try {
    const r = await fetch(`${SUPABASE.url}/auth/v1/token?grant_type=password`, {
      method: 'POST',
      headers: { apikey: SUPABASE.anon, 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: ROLES[rol].email, password: SUPABASE.demo }),
    });
    if (!r.ok) return null;
    const d = (await r.json()) as { access_token: string; expires_in: number; user: { id: string } };
    return { token: d.access_token, userId: d.user.id, expira: Date.now() + (d.expires_in - 60) * 1000 };
  } catch {
    return null; // sin red: sesión local
  }
}

export async function entrar(rol: Rol): Promise<Session> {
  const remoto = await loginDemo(rol);
  const s: Session = { rol, nombre: ROLES[rol].firma, modo: remoto ? 'compartido' : 'local', ...(remoto ?? {}) };
  guardarSesion(s);
  return s;
}

/** Token vigente para escribir en la mesa compartida (renueva en silencio si venció). */
export async function tokenVigente(s: Session): Promise<Session | null> {
  if (s.modo !== 'compartido') return null;
  if (s.token && s.expira && s.expira > Date.now()) return s;
  const remoto = await loginDemo(s.rol);
  if (!remoto) return null;
  const nueva = { ...s, ...remoto };
  guardarSesion(nueva);
  return nueva;
}
