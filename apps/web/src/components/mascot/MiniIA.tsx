import { useEffect, useId, useRef, useState } from 'react';
import type { MascotState } from '../../lib/mascot';

/**
 * Mini IA, mascota tecnológica de TVN, vectorizada a partir de public/brand/tvn/mini-ia.png: casco blanco redondeado,
 * visor azul noche, ojos y boca de luz cian, audífonos azules y antena con bombilla. La cara está separada en capas
 * (ojos, párpados, boca, cejas, antena, brillo) para que cada estado cambie de FORMA, no solo de color.
 * Decorativa por defecto: el estado real se comunica en texto en la interfaz.
 */
export function MiniIA({
  state = 'idle',
  size = 72,
  decorative = true,
  gaze = 0,
  className = '',
  testId,
}: {
  state?: MascotState;
  size?: number;
  decorative?: boolean;
  /** Mirada horizontal −1 (izquierda) … 1 (derecha); se usa en «escuchando» para seguir el cursor del campo. */
  gaze?: number;
  className?: string;
  testId?: string;
}) {
  const uid = 'mia' + useId().replace(/[^a-zA-Z0-9]/g, '');
  const blink = useBlink(state === 'idle' || state === 'escuchando');
  const g = Math.max(-1, Math.min(1, gaze));
  const eyeShift = state === 'escuchando' ? { x: g * 5, y: 4 } : state === 'pensando' ? { x: 3, y: -5 } : { x: 0, y: 0 };
  return (
    <svg
      viewBox="0 0 120 120"
      width={size}
      height={size}
      className={`mascot ${className}`}
      data-mascot-state={state}
      data-testid={testId}
      data-blink={blink ? 'true' : undefined}
      {...(decorative ? { 'aria-hidden': true, focusable: 'false' } : { role: 'img', 'aria-label': `Mini IA (${state})` })}
    >
      <defs>
        <linearGradient id={`${uid}-helmet`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#FFFFFF" />
          <stop offset="1" stopColor="#D9DEF0" />
        </linearGradient>
        <linearGradient id={`${uid}-visor`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#152067" />
          <stop offset="1" stopColor="#0A0F3D" />
        </linearGradient>
        <linearGradient id={`${uid}-tvn`} x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" stopColor="#8B3FD9" />
          <stop offset=".45" stopColor="#C13FD1" />
          <stop offset="1" stopColor="#28AAE1" />
        </linearGradient>
      </defs>
      <g className="mascot-body">
        {/* antena / accesorio */}
        <g className="mascot-antenna" data-part="antena">
          <rect x="57.5" y="10" width="5" height="16" rx="2.5" fill="#1F3FC4" />
          <circle className="mascot-bulb" cx="60" cy="10" r="7" fill="#8FE3FF" stroke="#1F3FC4" strokeWidth="2.5" />
        </g>
        {/* audífonos */}
        <rect x="7" y="44" width="16" height="34" rx="8" fill="#1F3FC4" />
        <rect x="97" y="44" width="16" height="34" rx="8" fill="#1F3FC4" />
        <rect x="11" y="50" width="8" height="22" rx="4" fill="none" stroke="#5FD0FF" strokeWidth="2.5" />
        <rect x="101" y="50" width="8" height="22" rx="4" fill="none" stroke="#5FD0FF" strokeWidth="2.5" />
        {/* casco */}
        <rect x="17" y="24" width="86" height="76" rx="34" fill={`url(#${uid}-helmet)`} stroke="#C3CAE6" strokeWidth="1.5" />
        <path className="mascot-shine" data-part="brillo" d="M33 38 Q40 30 52 29" stroke="#FFFFFF" strokeWidth="4" strokeLinecap="round" fill="none" opacity=".9" />
        {/* visor */}
        <rect className="mascot-visor" x="27" y="39" width="66" height="48" rx="20" fill={`url(#${uid}-visor)`} />
        <rect className="mascot-accent" x="27" y="39" width="66" height="48" rx="20" fill="none" stroke="#E52D27" strokeWidth="3" opacity="0" />
        {/* cara */}
        <g className="mascot-face" fill="none" stroke="#8FE3FF" strokeLinecap="round" strokeLinejoin="round">
          <g className="mascot-eyes" data-part="ojos" transform={`translate(${eyeShift.x} ${eyeShift.y})`}>
            <Eyes state={state} />
          </g>
          <g className="mascot-lids" data-part="parpados">
            <rect className="mascot-lid" x="39" y="49" width="16" height="0" fill="#0E1550" stroke="none" />
            <rect className="mascot-lid" x="65" y="49" width="16" height="0" fill="#0E1550" stroke="none" />
          </g>
          <g className="mascot-brows" data-part="cejas">
            <Brows state={state} />
          </g>
          <g className="mascot-mouth" data-part="boca">
            <Mouth state={state} />
          </g>
        </g>
        {state === 'bloqueo' && (
          <g className="mascot-shield" transform="translate(84 76)">
            <path d="M14 1 L26 6 V15 C26 22 20 27 14 29 C8 27 2 22 2 15 V6 Z" fill={`url(#${uid}-tvn)`} stroke="#FFFFFF" strokeWidth="2.5" />
            <path d="M9 15 l4 4 l7 -8" fill="none" stroke="#FFFFFF" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
          </g>
        )}
      </g>
    </svg>
  );
}

function Eyes({ state }: { state: MascotState }) {
  const glow = { fill: '#8FE3FF', stroke: 'none' } as const;
  switch (state) {
    case 'respondida': // ojos contentos ^ ^
      return (
        <>
          <path d="M40 60 Q47 50 54 60" strokeWidth="4.5" />
          <path d="M66 60 Q73 50 80 60" strokeWidth="4.5" />
        </>
      );
    case 'parcial': // un ojo normal, otro entrecerrado
      return (
        <>
          <rect x="43" y="50" width="8" height="14" rx="4" {...glow} />
          <path d="M66 58 Q73 54 80 58" strokeWidth="4.5" />
        </>
      );
    case 'error': // «x» suaves
      return (
        <>
          <path d="M42 51 L52 61 M52 51 L42 61" strokeWidth="4" />
          <path d="M68 51 L78 61 M78 51 L68 61" strokeWidth="4" />
        </>
      );
    case 'abstencion': // ojos amables, un poco más bajos
      return (
        <>
          <rect x="43" y="52" width="8" height="11" rx="4" {...glow} />
          <rect x="69" y="52" width="8" height="11" rx="4" {...glow} />
        </>
      );
    case 'bloqueo':
      return (
        <>
          <rect x="43" y="53" width="8" height="10" rx="3" {...glow} />
          <rect x="69" y="53" width="8" height="10" rx="3" {...glow} />
        </>
      );
    default: // idle, escuchando, pensando, contradicción: píldoras verticales como en la imagen
      return (
        <>
          <rect className="mascot-eye" x="43" y="49" width="8" height="15" rx="4" {...glow} />
          <rect className="mascot-eye" x="69" y="49" width="8" height="15" rx="4" {...glow} />
        </>
      );
  }
}

function Brows({ state }: { state: MascotState }) {
  if (state === 'parcial') return <path d="M65 44 Q73 39 80 43" strokeWidth="3" />; // una ceja levantada
  if (state === 'bloqueo')
    return (
      <>
        <path d="M40 45 L53 49" strokeWidth="3.5" />
        <path d="M80 45 L67 49" strokeWidth="3.5" />
      </>
    );
  if (state === 'contradiccion')
    return (
      <>
        <path d="M41 46 Q47 43 53 46" strokeWidth="3" />
        <path d="M67 46 Q73 43 79 46" strokeWidth="3" />
      </>
    );
  return null;
}

function Mouth({ state }: { state: MascotState }) {
  switch (state) {
    case 'pensando':
      return <circle cx="60" cy="75" r="3.5" strokeWidth="3" />;
    case 'respondida':
      return <path d="M46 70 Q60 84 74 70 Z" fill="#8FE3FF" strokeWidth="3" />;
    case 'parcial':
      return <path d="M50 75 Q60 79 71 71" strokeWidth="3.5" />;
    case 'contradiccion':
      return <path d="M48 75 Q53 71 58 75 T68 75 T74 74" strokeWidth="3" />;
    case 'abstencion':
      return <path d="M50 75 L70 75" strokeWidth="3.5" />;
    case 'bloqueo':
      return <path d="M52 76 L68 76" strokeWidth="4" />;
    case 'error':
      return <path d="M50 77 Q55 73 60 77 T70 77" strokeWidth="3" />;
    default:
      return <path d="M49 71 Q60 81 71 71" strokeWidth="3.5" />;
  }
}

/** Parpadeo aleatorio cada 4–6 s (solo en reposo/escucha y sin «reducir movimiento»). */
function useBlink(active: boolean): boolean {
  const [blink, setBlink] = useState(false);
  const timer = useRef<number | undefined>(undefined);
  useEffect(() => {
    if (!active || typeof window === 'undefined') return;
    if (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) return;
    let live = true;
    const loop = () => {
      timer.current = window.setTimeout(() => {
        if (!live) return;
        setBlink(true);
        window.setTimeout(() => live && setBlink(false), 140);
        loop();
      }, 4000 + Math.random() * 2000);
    };
    loop();
    return () => {
      live = false;
      window.clearTimeout(timer.current);
    };
  }, [active]);
  return blink;
}
