import { expect, it } from 'vitest';
import { socialVariants } from './social';

it('cada variante respeta su límite y siempre dice que es borrador', () => {
  const copy = 'Borrador para revisión: La Estrella reporta «Canal de Panamá evita nuevas restricciones y mantendrá 32 tránsitos hasta diciembre» [c1]. Evidencia insuficiente. Basado únicamente en titular/metadatos; pendiente de verificación.';
  const v = socialVariants(copy);
  expect(v.map((x) => x.red)).toEqual(['X', 'Instagram', 'TikTok']);
  for (const x of v) {
    expect(x.texto.length).toBeLessThanOrEqual(x.limite);
    expect(x.texto).toContain('Borrador, requiere revisión');
    expect(x.texto).not.toMatch(/\[c\d+\]/);
  }
});
