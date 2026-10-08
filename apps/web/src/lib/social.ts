// Variantes del copy para redes de TVN, derivadas SOLO del copy ya validado (no añaden hechos). Siempre borrador.
export type SocialVariant = { red: 'Instagram' | 'X' | 'TikTok'; limite: number; texto: string };

const ESTADO = '[Borrador, requiere revisión]';

function cut(text: string, max: number): string {
  if (text.length <= max) return text;
  const slice = text.slice(0, max - 1);
  const at = slice.lastIndexOf(' ');
  return (at > max * 0.6 ? slice.slice(0, at) : slice).replace(/[\s,;:.]+$/, '') + '…';
}

export function socialVariants(copy: string): SocialVariant[] {
  const base = copy.replace(/\s*\[c\d+\]/g, '').replace(/\s+/g, ' ').trim();
  if (!base) return [];
  const make = (red: SocialVariant['red'], limite: number, cola: string) => {
    const room = limite - ESTADO.length - cola.length - 2;
    return { red, limite, texto: `${ESTADO} ${cut(base, room)}${cola ? ' ' + cola : ''}` };
  };
  return [
    make('X', 280, '#TVNNoticias'),
    make('Instagram', 2200, '\n\n#TVN #Panamá #TVNNoticias'),
    make('TikTok', 150, '#TVN'),
  ];
}
