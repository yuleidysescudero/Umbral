import { cleanup, render } from '@testing-library/react';
import { afterEach, expect, it } from 'vitest';
import { MiniIA } from './MiniIA';
import { MASCOT_STATES } from '../../lib/mascot';

afterEach(cleanup);

it('cada estado cambia la forma de la cara (ojos o boca), no solo el color', () => {
  const shapes = new Set<string>();
  for (const s of MASCOT_STATES.filter((x) => x !== 'escuchando')) {
    const { container, unmount } = render(<MiniIA state={s} />);
    const svg = container.querySelector('svg')!;
    expect(svg.getAttribute('data-mascot-state')).toBe(s);
    shapes.add(svg.querySelector('[data-part="ojos"]')!.innerHTML + svg.querySelector('[data-part="boca"]')!.innerHTML + svg.querySelector('[data-part="cejas"]')!.innerHTML);
    unmount();
  }
  expect(shapes.size).toBe(MASCOT_STATES.length - 1);
});

it('decorativa: aria-hidden; informativa: role img con etiqueta', () => {
  const { container, rerender } = render(<MiniIA state="idle" />);
  expect(container.querySelector('svg')!.getAttribute('aria-hidden')).toBe('true');
  rerender(<MiniIA state="bloqueo" decorative={false} />);
  expect(container.querySelector('svg')!.getAttribute('role')).toBe('img');
});
