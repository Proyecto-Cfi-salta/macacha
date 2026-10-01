# Casilla de mail de contacto por organismo — Diseño

Fecha: 2026-10-01

## Objetivo

Que el aviso de una solicitud de contacto llegue a una **casilla de mail propia de cada organismo**,
cargada desde el panel admin en la sección **Contacto**, en lugar de depender de los emails de los
usuarios del panel.

## Contexto

- Hoy `contacto_repository.resolver_destinatarios` devuelve los emails de los admins activos del
  organismo del trámite; si no hay ninguno (o la solicitud no tiene organismo), los de los super
  admins.
- El envío (`agent/mail.py`) fallaba con el puerto 465 de producción por usar STARTTLS en vez de
  SSL implícito. Ese arreglo se hizo aparte (`SMTP_SSL` para 465, STARTTLS para el resto) y no es
  parte de este diseño; se lo menciona porque sin él ninguna casilla recibiría nada.

## Decisiones tomadas

1. **Destinatarios:** si el organismo tiene casilla, el aviso va **solo a esa casilla**. Si no la
   tiene, se mantiene el comportamiento actual (admins del organismo y, si no hay, super admins).
2. **Permisos:** el **super admin** ve y edita la casilla de todos los organismos; el **admin de
   organismo** ve y edita únicamente la de su organismo.

## Alcance

Incluido:

- Columna `organismos.email_contacto` (opcional) y su carga/edición desde Contacto.
- Cambio de `resolver_destinatarios` para usar la casilla.

Fuera de alcance:

- Más de una dirección por casilla (una sola por organismo).
- `Reply-To` con el email de la persona, envío en segundo plano y registro del resultado del envío
  (mejoras posibles del mismo flujo, no pedidas).
- Verificar que la casilla exista o enviar un mail de prueba al guardarla.
- Casilla para solicitudes sin organismo: siguen yendo a los super admins.

## Datos

`backend/db/schema.sql`, junto a las demás sentencias idempotentes:

```sql
ALTER TABLE organismos ADD COLUMN IF NOT EXISTS email_contacto TEXT;
ALTER TABLE organismos DROP CONSTRAINT IF EXISTS organismos_email_contacto_largo;
ALTER TABLE organismos ADD CONSTRAINT organismos_email_contacto_largo
    CHECK (email_contacto IS NULL OR char_length(email_contacto) <= 254);
```

`NULL` significa "sin casilla". Nunca se guarda una cadena vacía: vaciar el campo guarda `NULL`.

## Backend

### Envío

`resolver_destinatarios(conn, organismo_id)`:

1. Si `organismo_id` no es `None` y el organismo tiene `email_contacto`, devuelve `[email_contacto]`.
2. Si no, el comportamiento actual (admins activos del organismo; si no hay, super admins).

### API (requiere sesión de admin)

- `GET /admin/contacto/casillas`: lista `[{"id", "nombre", "email_contacto"}]` ordenada por nombre.
  Super admin: todos los organismos. Admin de organismo: solo el suyo.
- `PUT /admin/contacto/casillas/{organismo_id}` con cuerpo `{"email_contacto": str | null}`:
  - Un admin de organismo que pide un organismo distinto del suyo recibe **404** (mismo criterio que
    el resto de recursos ajenos); un organismo inexistente también devuelve 404.
  - `null` o una cadena vacía/solo espacios borran la casilla (se guarda `NULL`).
  - Un valor no vacío se recorta y se valida con el patrón `usuario@dominio.tld` (sin espacios, un
    solo `@`, un punto en el dominio) y un máximo de 254 caracteres; si no cumple, **422** sin
    escribir nada.
  - Responde `{"id", "nombre", "email_contacto"}` con el valor guardado.

## Frontend

En `/admin/contacto`, un bloque **"Casillas de mail de contacto"** sobre la lista de solicitudes:

- Una fila por organismo visible (todos para el super admin; uno para el admin de organismo) con el
  nombre, un campo de email y el botón **Guardar**.
- Una leyenda: "Si el organismo no tiene casilla, el aviso se envía a los emails de sus usuarios."
- Después de guardar, un aviso "Casilla guardada." o "Se quitó la casilla."; si falla, el mensaje del
  servidor. El botón está deshabilitado mientras guarda.
- Validación previa en el navegador con la misma regla, para avisar antes de enviar.

## Pruebas

- **pytest:** `resolver_destinatarios` con casilla, sin casilla (respaldo a admins y a super admins) y
  sin organismo; `GET` y `PUT` para ambos roles; 404 al editar un organismo ajeno o inexistente; 422
  por formato inválido y por más de 254 caracteres sin escribir; borrado con `null` y con cadena
  vacía; y que `POST /contacto` envía el mail a la casilla (con `enviar_mail` simulado).
- **vitest:** la validación de email del frontend, con la misma tabla de casos que el backend.
- **Verificación visual:** capturas de la pantalla Contacto como super admin y como admin de
  organismo, con la casilla vacía y cargada, contra la base de test.

## Despliegue

Orden obligatorio: **primero** aplicar `schema.sql` en la base de producción, **después** el backend
y **por último** el frontend. Si el backend sale antes que la columna, `POST /contacto` falla al
leer `email_contacto`. Las casillas arrancan vacías, así que mientras nadie las cargue el
comportamiento es el de hoy.

## Riesgos

- **Casilla mal escrita:** el aviso se pierde sin error visible, porque el envío falla en silencio.
  Se mitiga solo con la validación de formato; no se verifica que la casilla exista.
- **Cambio de comportamiento:** al cargar una casilla, los usuarios del organismo dejan de recibir el
  aviso por mail (siguen viendo la solicitud en el panel).
