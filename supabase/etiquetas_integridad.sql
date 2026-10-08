-- QA TVN 3.11 · Integridad del etiquetado humano (vista «Etiquetar» de Umbral MEGA).
-- Idempotente. Se aplica sobre la base compartida de la mesa (tabla public.etiquetas).
-- 1) Cada etiqueta guarda rol y sesión para auditar y descartar marcas.
alter table public.etiquetas add column if not exists rol text;
alter table public.etiquetas add column if not exists sesion text;
alter table public.etiquetas add column if not exists comentario text;
alter table public.etiquetas add column if not exists producto text;

-- 2) Límites de tamaño por campo (evita inyectar textos enormes por la anon key pública).
alter table public.etiquetas drop constraint if exists etiquetas_tamanos;
alter table public.etiquetas add constraint etiquetas_tamanos check (
  char_length(item_id) <= 120 and char_length(valor) <= 60 and char_length(persona) <= 80
  and char_length(coalesce(comentario, '')) <= 500 and char_length(coalesce(rol, '')) <= 20
  and char_length(coalesce(sesion, '')) <= 64 and char_length(coalesce(producto, '')) <= 20
) not valid;

-- 3) Solo inserción (sin UPDATE/DELETE) y el rol Jurado no etiqueta.
drop policy if exists "insertar propio" on public.etiquetas;
create policy "insertar propio" on public.etiquetas for insert to authenticated
  with check (
    usuario_id = auth.uid()
    and coalesce(auth.jwt() ->> 'email', '') <> 'jurado@rastro-demo.com'
    and coalesce(rol, '') <> 'jurado'
  );
drop policy if exists "actualizar" on public.etiquetas;
drop policy if exists "borrar" on public.etiquetas;
