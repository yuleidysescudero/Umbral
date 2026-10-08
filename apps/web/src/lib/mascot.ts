// Mini IA: estado de la mascota a partir de la respuesta de la API. La expresión acompaña; el estado real siempre
// se comunica en texto (Pill de la respuesta). Nunca es la única señal.
import type { QueryResponse } from './api/types';

export type MascotState =
  | 'idle'
  | 'escuchando'
  | 'pensando'
  | 'respondida'
  | 'parcial'
  | 'contradiccion'
  | 'abstencion'
  | 'bloqueo'
  | 'error';

export const MASCOT_STATES: MascotState[] = ['idle', 'escuchando', 'pensando', 'respondida', 'parcial', 'contradiccion', 'abstencion', 'bloqueo', 'error'];

/** Rechazos por seguridad o privacidad: la mascota pone «ceño firme y escudo», no cara de error. */
const BLOQUEO_RE = /inyecci|instrucci|reglas del sistema|configuraci[oó]n|privacidad|perfilamiento|sospechos|culpab/i;

export function mascotStateFor(r: Pick<QueryResponse, 'answerStatus' | 'abstentionReason' | 'warnings'>): MascotState {
  if (r.warnings?.includes('inyeccion_detectada')) return 'bloqueo';
  if (r.answerStatus === 'abstencion' && r.abstentionReason && BLOQUEO_RE.test(r.abstentionReason)) return 'bloqueo';
  switch (r.answerStatus) {
    case 'respondida':
      return 'respondida';
    case 'parcial':
      return 'parcial';
    case 'contradiccion':
      return 'contradiccion';
    default:
      return 'abstencion';
  }
}

/** Texto breve de la mascota (solo interfaz; el contenido de las respuestas sale de la API sin cambios). */
export const MASCOT_LINE: Record<MascotState, string> = {
  idle: 'Pregúntame por la agenda. Si no tengo evidencia, te lo digo.',
  escuchando: 'Te leo…',
  pensando: 'Buscando en el corpus…',
  respondida: 'Listo, aquí tienes con sus fuentes.',
  parcial: 'Encontré algo, pero no todo. Te marco lo que falta.',
  contradiccion: 'Ojo: las fuentes no coinciden. Te muestro ambas versiones.',
  abstencion: 'Con lo que tengo, no lo puedo afirmar. Te digo qué faltaría.',
  bloqueo: 'Eso no lo hago. Sigo con la parte que sí es una pregunta.',
  error: 'Se me cortó la conexión. Prueba otra vez en un momento.',
};
