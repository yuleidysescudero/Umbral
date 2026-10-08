import { useQuery } from '@tanstack/react-query';
import { Users } from 'lucide-react';
import { leerMesa, type Decision } from '../../lib/mesa';
import { fmtDateTime } from '../../lib/format';
import { REVIEW_LABEL } from '../../lib/labels';
import type { ReviewStatus } from '../../lib/api/types';
import { useApp } from '../context';
import { Card, ErrorBox, Loading, Notice, ReviewPill, SectionTitle } from '../ui';

const COLUMNAS: ReviewStatus[] = ['en_revision', 'requiere_evidencia', 'aprobado_como_borrador', 'descartado'];

/** Mesa compartida: estado vigente de cada caso según la última decisión del equipo (el historial completo no se borra). */
export function Mesa() {
  const { session, go } = useApp();
  const q = useQuery({
    queryKey: ['mesa', session?.modo],
    queryFn: () => (session ? leerMesa(session) : Promise.resolve(null)),
    refetchInterval: 20_000,
  });

  if (!session || session.modo !== 'compartido') {
    return (
      <Notice tone="info" title="Mesa compartida no disponible en esta sesión" testId="mesa-local">
        <p>Esta sesión trabaja solo en este navegador (sin conexión con la mesa del equipo). Tus revisiones siguen guardadas aquí y se pueden exportar desde Borradores.</p>
      </Notice>
    );
  }
  if (q.isLoading) return <Loading label="Cargando decisiones del equipo…" />;
  if (q.error) return <ErrorBox error={q.error} onRetry={() => void q.refetch()} />;
  const filas = q.data ?? [];
  const vigente = new Map<string, Decision>();
  for (const d of [...filas].reverse()) vigente.set(d.id_evento, d);
  const casos = [...vigente.values()];

  return (
    <div className="space-y-4" data-testid="mesa-view">
      <Card>
        <SectionTitle kicker="Control humano · equipo" heading>Mesa compartida</SectionTitle>
        <p className="text-sm text-ink-2">
          Lo que decidió cada persona responsable. <strong>Aprobar como borrador no es publicar.</strong> {filas.length} decisiones registradas sobre {casos.length} casos; se actualiza cada 20 s.
        </p>
      </Card>
      <div className="grid gap-4 lg:grid-cols-4">
        {COLUMNAS.map((col) => {
          const lista = casos.filter((c) => c.estado === col);
          return (
            <Card key={col} data-testid={`mesa-col-${col}`}>
              <div className="mb-3 flex items-center justify-between gap-2">
                <ReviewPill status={col} />
                <span className="text-sm font-semibold text-ink-3">{lista.length}</span>
              </div>
              <ul className="space-y-2">
                {lista.map((c) => (
                  <li key={c.id_evento}>
                    <button type="button" onClick={() => go({ view: 'ficha', topicId: c.id_evento })}
                      className="w-full border-2 border-ink bg-card p-2.5 text-left text-sm hover:bg-amber-50">
                      <span className="block font-semibold leading-snug">{c.titulo ?? c.id_evento}</span>
                      <span className="mt-1 block text-xs text-ink-3">{c.persona} · {fmtDateTime(c.created_at)}</span>
                      {c.nota && <span className="mt-1 block text-xs text-ink-2">«{c.nota}»</span>}
                    </button>
                  </li>
                ))}
                {lista.length === 0 && <li className="text-sm text-ink-3">Sin casos.</li>}
              </ul>
            </Card>
          );
        })}
      </div>
      <Card>
        <SectionTitle kicker="Trazabilidad">Historial del equipo</SectionTitle>
        <ol className="space-y-2 text-sm">
          {filas.slice(0, 50).map((d) => (
            <li key={d.id} className="flex flex-wrap items-center gap-2 border-b border-rule pb-2">
              <span className="text-ink-3">{fmtDateTime(d.created_at)}</span>
              <ReviewPill status={d.estado} />
              <strong>{d.persona}</strong>
              <span className="min-w-0 flex-1 truncate">{d.titulo ?? d.id_evento}</span>
              {d.nota && <span className="text-ink-2">— {d.nota}</span>}
            </li>
          ))}
          {filas.length === 0 && (
            <li className="flex items-center gap-2 text-ink-3"><Users size={16} aria-hidden="true" />Aún no hay decisiones. Revisa un caso en Borradores y aparecerá aquí ({REVIEW_LABEL.en_revision.toLowerCase()}, etc.).</li>
          )}
        </ol>
      </Card>
    </div>
  );
}
