// Tema claro/oscuro (la marca TVN vive en oscuro). Preferencia por navegador en localStorage, siempre con try/catch.
import { readLocal, writeLocal } from './storage';

export type Theme = 'light' | 'dark';
const KEY = 'umbral.theme';

export function readTheme(): Theme {
  return readLocal(KEY, 'light') === 'dark' ? 'dark' : 'light';
}

export function applyTheme(theme: Theme): void {
  document.documentElement.dataset.theme = theme;
  document.querySelector('meta[name="theme-color"]')?.setAttribute('content', theme === 'dark' ? '#0B0640' : '#110862');
  writeLocal(KEY, theme);
}
