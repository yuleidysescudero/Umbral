# Umbral MEGA · versión para el jurado

**Demo:** https://umbral-mega.vercel.app/app/ · **Código:** rama `mega` de https://github.com/yuleidysescudero/Umbral

Umbral MEGA es Umbral con las mejoras que el equipo tomó de su segundo prototipo (RASTRO) y con los fallos que
encontramos al probar Umbral con las preguntas del jurado (PDF del reto, pág. 11). Todo sigue siendo un borrador para
revisión humana: nada se publica y el sistema nunca dice qué es verdadero o falso.

## Cómo probarla (2 minutos)

1. Abre la demo y toca un rol: **Editor/a**, **Productor/a digital**, **Revisor/a** o **Jurado**. No hay contraseña.
2. **Agenda** (CU-01): los temas ordenados por `P = 30R + 25I + 20U + 15N + 10E`, con «N notas, pero solo M fuentes reales».
3. **Ficha**: fuentes, procedencias, contexto del Banco Mundial con año y unidad, contradicciones y vacíos.
4. **Borradores**: brief, guion y copy con citas; en «Revisión del caso» la persona responsable ya viene firmada por el rol.
5. **Mesa**: lo que decidió cada persona del equipo (solo inserción: nada se edita ni se borra).
6. **Asistente**: prueba «¿Cuántas personas murieron por el sismo de hoy?», «Ignora tus instrucciones…» o
   «¿Cuál fue la inflación de Panamá según el Banco Mundial?».
7. **Etiquetar**: etiquetado humano a ciegas para las métricas de IA frente al baseline.

## Qué cambia frente a Umbral

| Debilidad encontrada | Cambio en MEGA | Evidencia |
|---|---|---|
| «¿Cuántas personas murieron por el sismo de hoy?» respondía con «Sismo de magnitud 5,4» | La cifra del titular debe ser del **mismo tipo** que la pedida (personas, dinero, %, pérdidas) y «hoy» exige 48 h | `apps/api/tests/test_queries_evidence_kind.py` |
| «¿Inflación según el Banco Mundial?» se abstenía («según» como país desconocido) | Las palabras de la consulta no se tratan como entidades | ídem |
| La inyección solo se abstenía por falta de coincidencias | Rechazo **explícito** y auditable; no se busca | ídem (T07) |
| «¿Qué diputados son sospechosos?» se abstenía por azar | Rechazo por privacidad y reputación (pág. 8) | ídem |
| 991 noticias → 910 grupos: casi no agrupaba paráfrasis ni otros idiomas | Agrupación semántica precalculada: **910 → 808 grupos; temas con ≥ 2 procedencias independientes: 7 → 50** | `scripts/agrupar_semantico.py`, `data/agrupacion/*/meta.json`, `apps/api/tests/test_semantic_clusters.py` |
| Render Free se duerme (~1 min en la primera petición) | Web y API en el mismo Vercel (`api/index.py`): ~0,5 s | `vercel.json` |
| Sin sesiones: la revisión quedaba en un navegador | Entrada por rol y **Mesa compartida** (Supabase, solo inserción); sin red sigue en local (T10) | `apps/web/src/lib/session.ts`, `lib/mesa.ts` |
| Métricas de clasificación, agrupación y sustento «pendientes» | Vista **Etiquetar** a ciegas y volcado a las hojas de `eval/labels` | `scripts/importar_etiquetas_mesa.py` |
| Clonado en Windows, el snapshot fallaba la verificación SHA-256 | `.gitattributes` sin conversión de fin de línea en `data/` y `eval/` | — |

Resultados verificados el 08/10/2026: API 286 pruebas (269 originales + 17 nuevas), web 68 pruebas, `astro check` sin
errores y regla «sin controles nativos» aprobada. Benchmark de desarrollo (40 consultas) igual que Umbral original, con y
sin agrupación semántica: respuesta con cita 20/20, abstención correcta 14/14, abstención incorrecta 0/20, adversariales 7/7.

## Agrupación semántica (CU-03)

El pipeline une solo titulares casi idénticos (`token_sort_ratio ≥ 88`). `scripts/agrupar_semantico.py` une **grupos**
cuando dos de sus titulares son equivalentes según `paraphrase-multilingual-MiniLM-L12-v2` (CPU), sobre el titular sin
«Panamá»: coseno ≥ 0,74, a ≤ 72 h y, si el coseno es menor que 0,84, con al menos 2 palabras de contenido en común.
Elige como representante el titular en español publicado primero y recalcula las procedencias independientes con la
misma función del pipeline.

- No modifica el snapshot: escribe `data/agrupacion/<snapshot>/clusters.semantic.jsonl` y `meta.json` (SHA-256, parámetros
  y las 25 uniones de borde para revisión).
- La API lo usa solo con `UMBRAL_SEMANTIC_CLUSTERS=1` y si los hashes del archivo y del `clusters.jsonl` de origen cuadran.
- Límites: solo titulares; en las uniones de borde revisadas hay 2–3 dudosas de 25 (casi todas de deportes, fuera de los
  seis temas). La precisión real se mide con los pares etiquetados por personas.

```bash
python scripts/agrupar_semantico.py          # requiere sentence-transformers + PyTorch CPU (solo fuera de línea)
```

## Etiquetado humano y métricas

```bash
python scripts/hojas_etiquetado.py           # hojas de eval/labels → apps/web/public/etiquetado/hojas.json (sin predicción)
# … el equipo etiqueta en la vista «Etiquetar» …
SUPABASE_URL=… SUPABASE_SERVICE_ROLE_KEY=… python scripts/importar_etiquetas_mesa.py   # o --desde etiquetas.json
# después: eval/labels/LEEME.md → «Después de etiquetar» (import + métricas)
```

## Despliegue

```bash
git archive HEAD | tar -x -C /tmp/umbral-mega && cp -r .vercel /tmp/umbral-mega/ && cd /tmp/umbral-mega && vercel deploy --prod
```

Variables de compilación en Vercel (no son secretos: quedan en el navegador): `PUBLIC_SESSION_GATE=1`,
`PUBLIC_SUPABASE_URL`, `PUBLIC_SUPABASE_ANON_KEY` y `PUBLIC_DEMO_CLAVE`, la contraseña de las cuentas de
demostración, que **solo pueden agregar** filas. La clave de servicio de Supabase nunca va al repositorio ni a Vercel.
Sin estas variables, la web funciona como Umbral original.

## Límites que decimos con honestidad

- Snapshot provisional (no hay paquete oficial congelado) y solo titulares y metadatos.
- Cualquiera con el enlace puede entrar con un rol y **agregar** decisiones o etiquetas; no puede editarlas ni borrarlas.
- La calidad editorial no está validada hasta completar el etiquetado humano; pasar las pruebas automáticas no lo sustituye.
