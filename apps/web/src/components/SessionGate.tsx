import { useState } from 'react';
import { BadgeCheck, Gavel, Newspaper, Smartphone, type LucideIcon } from 'lucide-react';
import { compartidoDisponible, entrar, ROLES, type Rol, type Session } from '../lib/session';
import { Notice } from './ui';

const ICONO: Record<Rol, LucideIcon> = { editor: Newspaper, productor: Smartphone, revisor: BadgeCheck, jurado: Gavel };

/** Entrada por rol: un toque y adentro. La firma del rol queda como persona responsable de cada revisión. */
export function SessionGate({ onEnter }: { onEnter: (s: Session) => void }) {
  const [ocupado, setOcupado] = useState<Rol | null>(null);

  async function elegir(rol: Rol) {
    setOcupado(rol);
    try {
      onEnter(await entrar(rol));
    } finally {
      setOcupado(null);
    }
  }

  return (
    <div data-testid="session-gate" className="comic-sheet mx-auto max-w-4xl px-4 py-10">
      <a href="/" className="comic-brand text-4xl" aria-label="Umbral, inicio">Umbral<span className="text-amber-600">.</span></a>
      <p className="kicker mt-6">De la señal a la decisión · TVN Media</p>
      <h1 className="font-display text-4xl font-bold leading-tight md:text-5xl">¿Con qué rol entras a la mesa?</h1>
      <p className="mt-2 max-w-2xl text-ink-2">
        Toca tu rol: no hace falta contraseña. Tu rol firma cada revisión como persona responsable
        {compartidoDisponible ? ' y la decisión se comparte con todo el equipo.' : '.'}
      </p>
      <div className="mt-6 grid gap-4 sm:grid-cols-2">
        {(Object.keys(ROLES) as Rol[]).map((rol) => {
          const Ico = ICONO[rol];
          return (
            <button
              key={rol}
              type="button"
              data-testid={`session-role-${rol}`}
              disabled={ocupado !== null}
              onClick={() => void elegir(rol)}
              className={`comic-panel group flex items-start gap-4 p-5 text-left transition-transform hover:-translate-y-0.5 disabled:opacity-60 ${rol === 'jurado' ? 'bg-amber-100' : ''}`}
            >
              <span className="grid h-12 w-12 shrink-0 place-items-center border-2 border-ink bg-amber-300">
                <Ico size={22} aria-hidden="true" />
              </span>
              <span>
                <span className="block font-display text-2xl font-bold leading-tight">{ocupado === rol ? 'Entrando…' : ROLES[rol].nombre}</span>
                <span className="mt-1 block text-sm text-ink-2">{ROLES[rol].descripcion}</span>
              </span>
            </button>
          );
        })}
      </div>
      <div className="mt-6">
        <Notice tone="info" title="Qué se guarda y dónde">
          <p>
            Borradores y pesos se guardan en este navegador.{' '}
            {compartidoDisponible
              ? 'Las decisiones de revisión también se copian a la mesa compartida (solo se pueden agregar, nunca editar ni borrar).'
              : 'Sin conexión, todo sigue funcionando en este navegador.'}{' '}
            No se guardan datos personales: solo la firma del rol.
          </p>
        </Notice>
      </div>
    </div>
  );
}
