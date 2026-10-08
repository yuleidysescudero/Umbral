import { useState } from 'react';
import { BadgeCheck, Gavel, Newspaper, Smartphone, type LucideIcon } from 'lucide-react';
import { compartidoDisponible, entrar, ROLES, type Rol, type Session } from '../lib/session';
import { Notice } from './ui';
import { MiniIA } from './mascot/MiniIA';
import { TvnLogo } from './brand/TvnLogo';

const ICONO: Record<Rol, LucideIcon> = { editor: Newspaper, productor: Smartphone, revisor: BadgeCheck, jurado: Gavel };
const DISCLAIMER = 'Prototipo de hackIAthon para TVN Media. No es un producto oficial de Televisora Nacional, S.A.';

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
    <div data-testid="session-gate" className="min-h-screen">
      <header className="tvn-masthead">
        <div className="mx-auto flex max-w-4xl items-center justify-between gap-3 px-4 py-3">
          <a href="/" className="tvn-brand" aria-label="Umbral × TVN, inicio">
            <TvnLogo size={40} />
            <span className="tvn-brand-divider" aria-hidden="true" />
            <span>
              <span className="tvn-brand-name">Umbral</span>
              <span className="tvn-brand-sub">Agenda editorial</span>
            </span>
          </a>
        </div>
      </header>
      <main className="mx-auto max-w-4xl px-4 py-8">
        <div className="flex flex-wrap items-center gap-5">
          <MiniIA size={110} state="idle" />
          <div className="min-w-0 flex-1">
            <p className="kicker">De la señal a la decisión · TVN Media</p>
            <h1 className="font-display text-3xl leading-tight md:text-4xl">¿Con qué rol entras a la mesa?</h1>
            <p className="mt-2 max-w-2xl text-ink-2">
              Toca tu rol: no hace falta contraseña. Tu rol firma cada revisión como persona responsable
              {compartidoDisponible ? ' y la decisión se comparte con todo el equipo.' : '.'}
            </p>
          </div>
        </div>
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
                className={`comic-panel group flex items-start gap-4 p-5 text-left transition-transform hover:-translate-y-0.5 disabled:opacity-60 ${rol === 'jurado' ? 'bg-amber-50' : ''}`}
              >
                <span className="grid h-12 w-12 shrink-0 place-items-center rounded-full border-2 border-tvn-night text-white" style={{ background: 'var(--gradient-tvn-strong)' }}>
                  <Ico size={22} aria-hidden="true" />
                </span>
                <span>
                  <span className="block font-display text-xl leading-tight text-ink">{ocupado === rol ? 'Entrando…' : ROLES[rol].nombre}</span>
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
        <p className="mt-6 text-sm text-ink-3" data-testid="gate-disclaimer">{DISCLAIMER}</p>
      </main>
    </div>
  );
}
