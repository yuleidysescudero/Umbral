import { useMemo, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { ChevronLeft, ChevronRight, Download, EyeOff, Layers, Quote, Tag } from 'lucide-react';
import { cargarHojas, guardarEtiqueta, listarEtiquetas, vigentes, type TipoEtiqueta } from '../../lib/etiquetas';
import { useApp } from '../context';
import { Button, Card, ErrorBox, Loading, Notice, SectionTitle, inputCls } from '../ui';

const OPCIONES: Record<TipoEtiqueta, { valor: string; texto: string }[]> = {
  tema: [
    { valor: 'economia', texto: 'Economía' }, { valor: 'logistica_canal', texto: 'Logística / Canal' },
    { valor: 'turismo', texto: 'Turismo' }, { valor: 'servicios_publicos', texto: 'Servicios públicos' },
    { valor: 'eventos_naturales', texto: 'Eventos naturales' }, { valor: 'regulacion', texto: 'Regulación' },
    { valor: 'indeterminado', texto: 'Ninguno de los seis' }, { valor: 'no_se', texto: 'No sé' },
  ],
  par: [{ valor: 'si', texto: 'Sí, el mismo hecho' }, { valor: 'no', texto: 'No, son distintos' }, { valor: 'no_se', texto: 'No sé' }],
  afirmacion: [
    { valor: 'respaldada', texto: 'Respaldada por el titular citado' }, { valor: 'no_respaldada', texto: 'No respaldada' },
    { valor: 'cita_incorrecta', texto: 'Cita incorrecta' }, { valor: 'no_se', texto: 'No sé' },
  ],
};
const MODOS: { tipo: TipoEtiqueta; nombre: string; icono: typeof Tag; ayuda: string }[] = [
  { tipo: 'tema', nombre: 'Temas', icono: Tag, ayuda: 'Elige el tema principal del titular. Si encaja en dos, elige el principal y menciona el otro en el comentario.' },
  { tipo: 'par', nombre: '¿Mismo hecho?', icono: Layers, ayuda: 'No basta con el mismo tema general: ¿informan sobre el mismo hecho concreto? Una copia de agencia cuenta como «sí».' },
  { tipo: 'afirmacion', nombre: 'Afirmaciones', icono: Quote, ayuda: 'Compara la frase con el titular citado. Un titular solo respalda que un medio reportó algo.' },
];

/** Etiquetado humano a ciegas: no se muestra la predicción del sistema (sesgo de anclaje). */
export function Etiquetar() {
  const { session } = useApp();
  const qc = useQueryClient();
  const hojas = useQuery({ queryKey: ['hojas'], queryFn: cargarHojas, staleTime: Infinity });
  const etqs = useQuery({ queryKey: ['etiquetas', session?.modo], queryFn: () => listarEtiquetas(session ?? null), refetchInterval: 30_000 });
  const [tipo, setTipo] = useState<TipoEtiqueta>('tema');
  const [pos, setPos] = useState(0);
  const [comentario, setComentario] = useState('');
  const [error, setError] = useState<unknown>(null);
  const [guardando, setGuardando] = useState(false);
  const mapa = useMemo(() => vigentes(etqs.data ?? []), [etqs.data]);

  if (hojas.isLoading || etqs.isLoading) return <Loading label="Cargando hojas de etiquetado…" />;
  if (hojas.error) return <ErrorBox error={hojas.error} />;
  const h = hojas.data!;
  const lista = h[tipo];
  const i = Math.min(pos, lista.length - 1);
  const item = lista[i];
  const hechos = (t: TipoEtiqueta) => h[t].filter((x) => mapa.has(`${t}:${x.id}`)).length;
  const actual = item ? mapa.get(`${tipo}:${item.id}`) : undefined;

  async function marcar(valor: string) {
    if (!session || !item) return;
    setGuardando(true); setError(null);
    try {
      await guardarEtiqueta(session, tipo, item.id, valor, comentario.trim());
      setComentario('');
      await qc.invalidateQueries({ queryKey: ['etiquetas'] });
      const siguiente = lista.findIndex((x, n) => n > i && !mapa.has(`${tipo}:${x.id}`));
      setPos(siguiente >= 0 ? siguiente : Math.min(i + 1, lista.length - 1));
    } catch (e) { setError(e); } finally { setGuardando(false); }
  }

  function exportar() {
    const blob = new Blob([JSON.stringify({ snapshotId: h.snapshotId, etiquetas: etqs.data ?? [] }, null, 1)], { type: 'application/json' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob); a.download = `etiquetas.${h.snapshotId}.json`; a.click();
    URL.revokeObjectURL(a.href);
  }

  return (
    <div className="space-y-4" data-testid="etiquetar-view">
      <Card>
        <SectionTitle kicker="Evaluación reproducible · pág. 9 del reto" heading aside={
          <Button icon={Download} onClick={exportar} data-testid="etiquetas-export">Descargar etiquetas</Button>
        }>Etiquetado humano</SectionTitle>
        <p className="text-sm text-ink-2">
          Con estas etiquetas se calculan macro-F1 (temas), precisión y recall (agrupación) y el sustento de afirmaciones frente al baseline.
          <strong> Se etiqueta a ciegas:</strong> no se muestra lo que predijo el sistema. Si dudas, «No sé» es mejor que adivinar.
        </p>
        <div className="mt-3 grid gap-2 sm:grid-cols-3">
          {MODOS.map(({ tipo: t, nombre, icono: Ico }) => (
            <button key={t} type="button" data-testid={`etiquetar-modo-${t}`} onClick={() => { setTipo(t); setPos(0); }}
              className={`border-2 border-ink p-3 text-left ${t === tipo ? 'bg-amber-200' : 'bg-card hover:bg-amber-50'}`}>
              <span className="flex items-center gap-2 font-display text-lg font-bold"><Ico size={18} aria-hidden="true" />{nombre}</span>
              <span className="text-sm">{hechos(t)} / {h[t].length} etiquetados</span>
              <span className="mt-1 block h-2 border border-ink bg-card"><span className="block h-full bg-amber-500" style={{ width: `${(100 * hechos(t)) / (h[t].length || 1)}%` }} /></span>
            </button>
          ))}
        </div>
      </Card>

      {item && (
        <Card data-testid="etiquetar-item">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2 text-sm text-ink-3">
            <span className="flex items-center gap-1.5"><EyeOff size={15} aria-hidden="true" />A ciegas · {i + 1} de {lista.length}</span>
            <span className="flex gap-1">
              <Button variant="ghost" icon={ChevronLeft} disabled={i === 0} onClick={() => setPos(i - 1)} aria-label="Anterior" />
              <Button variant="ghost" icon={ChevronRight} disabled={i >= lista.length - 1} onClick={() => setPos(i + 1)} aria-label="Siguiente" />
            </span>
          </div>
          <p className="mb-3 text-sm text-ink-2">{MODOS.find((m) => m.tipo === tipo)!.ayuda}</p>
          {tipo === 'tema' && 'texto' in item && (
            <p className="font-display text-2xl font-bold leading-snug">{item.texto}{'medio' in item && item.medio ? <span className="block text-sm font-normal text-ink-3">{item.medio}</span> : null}</p>
          )}
          {tipo === 'par' && 'a' in item && (
            <div className="grid gap-3 md:grid-cols-2">
              <p className="border-2 border-ink bg-card p-3 font-semibold">{item.a}</p>
              <p className="border-2 border-ink bg-card p-3 font-semibold">{item.b}</p>
            </div>
          )}
          {tipo === 'afirmacion' && 'titularCitado' in item && (
            <div className="grid gap-3 md:grid-cols-2">
              <div className="border-2 border-ink bg-card p-3"><p className="kicker">Afirmación del borrador</p><p className="font-semibold">{item.texto}</p></div>
              <div className="border-2 border-ink bg-amber-50 p-3"><p className="kicker">Titular citado · {item.medio ?? item.cita}</p><p className="font-semibold">{item.titularCitado ?? 'Titular no encontrado en el snapshot'}</p></div>
            </div>
          )}
          <div className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
            {OPCIONES[tipo].map((o) => (
              <Button key={o.valor} variant={actual?.valor === o.valor ? 'primary' : 'secondary'}
                disabled={guardando || !session} onClick={() => void marcar(o.valor)} data-testid={`etiqueta-${o.valor}`}>{o.texto}</Button>
            ))}
          </div>
          <input className={`${inputCls} mt-3`} placeholder="Comentario opcional (se guarda con la etiqueta)" value={comentario}
            onChange={(e) => setComentario(e.target.value)} aria-label="Comentario" />
          <p className="mt-2 text-xs text-ink-3">
            Etiqueta: <strong>{session?.nombre}</strong>{actual ? ` · ya etiquetado como «${actual.valor}» por ${actual.persona}` : ''} ·{' '}
            {session?.modo === 'compartido' ? 'se guarda en la mesa compartida.' : 'se guarda en este navegador; descárgalas al terminar.'}
          </p>
          {error ? <div className="mt-2"><ErrorBox error={error} /></div> : null}
        </Card>
      )}
      <Notice tone="info" title="Después de etiquetar">
        <p>
          <code>python scripts/importar_etiquetas_mesa.py</code> vuelca las etiquetas a <code>eval/labels/*.csv</code> y luego se siguen
          los pasos de <code>eval/labels/LEEME.md</code> para calcular las métricas sin inventar nada.
        </p>
      </Notice>
    </div>
  );
}
