import { describe, expect, it } from 'vitest';
import { mascotStateFor, MASCOT_LINE, MASCOT_STATES } from './mascot';

const base = { abstentionReason: null, warnings: [] as string[] };

describe('mascota: estado de la API → expresión', () => {
  it('mapea cada answerStatus', () => {
    expect(mascotStateFor({ ...base, answerStatus: 'respondida' })).toBe('respondida');
    expect(mascotStateFor({ ...base, answerStatus: 'parcial' })).toBe('parcial');
    expect(mascotStateFor({ ...base, answerStatus: 'contradiccion' })).toBe('contradiccion');
    expect(mascotStateFor({ ...base, answerStatus: 'abstencion', abstentionReason: 'no hay evidencia suficiente' })).toBe('abstencion');
  });
  it('inyección o privacidad → bloqueo (aunque la parte legítima se responda)', () => {
    expect(mascotStateFor({ ...base, answerStatus: 'respondida', warnings: ['inyeccion_detectada'] })).toBe('bloqueo');
    expect(mascotStateFor({ ...base, answerStatus: 'abstencion', abstentionReason: 'no señalo personas como sospechosas (privacidad y reputación)' })).toBe('bloqueo');
    expect(mascotStateFor({ ...base, answerStatus: 'abstencion', abstentionReason: 'la consulta intenta cambiar las reglas del sistema' })).toBe('bloqueo');
  });
  it('cada estado tiene un texto de interfaz (la expresión nunca es la única señal)', () => {
    for (const s of MASCOT_STATES) expect(MASCOT_LINE[s].length).toBeGreaterThan(5);
  });
});
