# Deploy de Macacha en Dokploy

Checklist para llevar Macacha a producción. Dokploy ya está instalado y
corriendo en el servidor. Ver el diseño completo en
`docs/superpowers/specs/2026-07-30-deploy-dokploy-design.md`.

**Antes de empezar:** creá ya mismo los registros DNS del paso 6
(`macacha.saltia.com.ar` y `api.macacha.saltia.com.ar` apuntando a la IP
del servidor) — podés hacerlo en paralelo con todo lo demás, así ya están
resueltos para cuando llegues a los pasos 4 y 5 y Dokploy intente emitir
el certificado SSL. Si igualmente llegás a esos pasos antes de que el DNS
propague, el primer intento de certificado va a fallar — forzá un
redeploy de la Application una vez que el dominio resuelva para que
Dokploy reintente.

## 1. Generar el secreto de producción

`ADMIN_JWT_SECRET` de producción tiene que ser distinto al de desarrollo:

```bash
openssl rand -hex 32
```

Guardá el resultado — se usa en el paso 4.

## 2. Crear la Database en Dokploy

1. En el proyecto de Dokploy, crear un recurso **Database** → Postgres.
2. Imagen: `pgvector/pgvector:pg16` (no la imagen default de Postgres —
   necesita la extensión pgvector).
3. Una vez creada, copiar la connection string interna que da Dokploy
   (la vas a necesitar en el paso 4).
4. Aplicar el esquema por primera vez, desde tu máquina (necesita
   conexión de red hacia la base — Dokploy suele tener una opción para
   exponer el puerto temporalmente). Este mismo comando hay que volverlo
   a correr más adelante cada vez que `schema.sql` cambie — ver la nota
   del punto 6:

   ```bash
   psql "<connection-string-de-produccion>" -f backend/db/schema.sql
   ```

5. Si es la primera vez que se aplica este cambio de schema (es decir, ya
   había admins creados con la versión anterior), promové el admin
   existente a super_admin:

   ```bash
   psql "<connection-string-de-produccion>" -c "UPDATE admins SET rol = 'super_admin' WHERE email = 'admin@macacha.gob.ar';"
   ```

6. **Instrucción permanente — cada vez que `schema.sql` cambie:** todas
   las sentencias de `backend/db/schema.sql` usan
   `CREATE TABLE IF NOT EXISTS`, así que el comando del paso 4 es
   idempotente — se puede volver a correr las veces que haga falta sin
   duplicar nada ni romper lo existente. Cuando una feature ya mergeada a
   `main` agrega una tabla o columna nueva a `schema.sql`, hay que volver
   a correr, contra la base de producción:

   ```bash
   psql "<connection-string-de-produccion>" -f backend/db/schema.sql
   ```

   antes de que esa feature funcione en producción — el auto-deploy en
   push a `main` (sección 4) actualiza el código del backend, pero nunca
   corre este comando por vos. Por ejemplo: la feature de "contacto a un
   humano" agrega la tabla `solicitudes_contacto`; sin volver a correr
   este comando, `POST /contacto` y `/admin/contacto*` van a devolver 500
   en producción.

   Lo mismo vale para el feedback de respuestas (botones 👍/👎 del chat):
   agrega la tabla `feedback_respuestas`. Orden obligatorio: **primero**
   correr el comando, **después** desplegar el backend y por último el
   frontend. Si el backend sale antes que la tabla, `POST /contacto`,
   `GET /sesiones/{id}/mensajes`, `/admin/sesiones*` y
   `/admin/feedback/metricas` devuelven 500 (todos leen el historial con un
   `JOIN` a la tabla nueva); si el frontend sale antes que el backend, los
   votos fallan con el aviso "No se pudo enviar tu opinión".

   La casilla de mail de contacto por organismo agrega la columna
   `organismos.email_contacto`. Mismo orden obligatorio: **primero** correr
   el comando, **después** desplegar el backend y por último el frontend. Si
   el backend sale antes que la columna, `POST /contacto` y
   `/admin/contacto/casillas` devuelven 500 (leen `email_contacto`). Las
   casillas arrancan vacías, así que hasta que alguien las cargue desde
   Contacto el aviso sigue yendo a los emails de los usuarios del organismo.
   Además, el servidor SMTP de producción usa el puerto 465 (SSL implícito):
   el backend lo soporta desde el arreglo de `enviar_mail`; con otro puerto se
   usa STARTTLS.

   La consulta por voz (`POST /audio/transcribe`) **no cambia la base de datos**. Orden: **primero** el
   backend, **después** el frontend (si el frontend sale antes, el botón del micrófono mostraría "No se pudo
   transcribir el audio"). Usa `OPENAI_API_KEY` y tiene variables opcionales: `AUDIO_TRANSCRIPTION_MODEL`
   (por defecto `gpt-4o-transcribe`), `AUDIO_TRANSCRIPTION_SECONDARY_MODEL` (`gpt-4o-mini-transcribe`),
   `AUDIO_TRANSCRIPTION_CONSENSUS_THRESHOLD` (`0.66`), `AUDIO_MAX_BYTES` (4 MiB; el frontend corta la grabación a los 2 minutos),
   `AUDIO_RATE_LIMIT_PER_MINUTE` (6 por IP; `0` lo desactiva) y `AUDIO_PROXY_HOPS` (1: cantidad de proxies
   de confianza delante del backend, para leer la IP real desde `X-Forwarded-For`; si en producción hay más
   de un proxy delante, hay que subirlo). El límite vive en la memoria del proceso: si el backend corre con
   varios procesos, cada uno cuenta aparte. Los audios se envían a OpenAI para transcribirlos y no se guardan
   en Macacha. El frontend manda `Permissions-Policy: microphone=(self)`; si hay un proxy que agrega ese
   encabezado con otro valor, el navegador bloqueará el micrófono.

   La lista de contacto guarda quién resolvió cada solicitud: agrega las
   columnas `solicitudes_contacto.resuelto_por_email` y `resuelto_en`. Mismo
   orden obligatorio: **primero** correr el comando de esquema, **después**
   el backend y por último el frontend. Si el backend sale antes, `GET
   /admin/contacto` y el detalle devuelven 500 (leen las columnas nuevas). Las
   solicitudes que ya estaban resueltas muestran "Sin registro".

## 3. Push a GitHub

Si todavía no existe el repo remoto, creá uno privado (desde la web de
GitHub o con `gh repo create sebamasaguer/macacha --private`) y agregá el
remote antes de pushear:

```bash
git remote add origin https://github.com/sebamasaguer/macacha.git
git push -u origin main
```

## 4. Crear la Application del backend en Dokploy

1. Conectar Dokploy al repo `https://github.com/sebamasaguer/macacha.git`.
2. Tipo: Application, build desde Dockerfile.
3. Son dos campos separados, ambos relativos a la raíz del repo (si
   ponés solo `backend` en el campo de Dockerfile Path, Dokploy busca un
   archivo llamado literalmente `backend` y falla con "failed to read
   dockerfile: open backend: no such file or directory"):
   - **Dockerfile Path:** `backend/Dockerfile`
   - **Docker Context Path:** `backend`
4. Dominio: `api.macacha.saltia.com.ar`.
5. Variables de entorno:

   | Variable | Valor |
   |---|---|
   | `DATABASE_URL` | connection string de la Database del paso 2 |
   | `OPENAI_API_KEY` | tu key real de producción |
   | `GEMINI_API_KEY` | opcional |
   | `ADMIN_JWT_SECRET` | el generado en el paso 1 |
   | `FRONTEND_ORIGIN` | `https://macacha.saltia.com.ar` |
   | `COOKIE_DOMAIN` | `macacha.saltia.com.ar` (sin esto la cookie de sesión del admin queda atada a `api.…` y el middleware del frontend no la ve: el login vuelve al formulario) |
   | `SMTP_HOST` | host del servidor SMTP — sin default, obligatorio para que el mail de "contacto a un humano" funcione |
   | `SMTP_PORT` | puerto SMTP — sin default, obligatorio (usar `587` salvo que el proveedor indique otro) |
   | `SMTP_USER` | usuario SMTP — sin default, obligatorio |
   | `SMTP_PASSWORD` | contraseña SMTP — sin default, obligatoria |
   | `SMTP_FROM` | remitente de los mails de notificación — sin default, obligatorio |

   Las cinco variables `SMTP_*` son obligatorias: `backend/agent/mail.py`
   las lee con `os.environ[...]` directo, sin ningún fallback en el código.
   Si falta alguna, el envío de mail lanza `KeyError`, pero el endpoint
   `POST /contacto` sigue respondiendo 200 igual (el envío de mail es
   best-effort y no rompe la respuesta al usuario) — ningún admin va a
   recibir la notificación y no habrá ningún error visible salvo en los
   logs del backend (`logger.exception(...)`), así que verificar las
   cinco variables ANTES de dar por buena la sección de contacto en
   producción.

6. Activar auto-deploy (webhook) en push a `main`.

## 5. Crear la Application del frontend en Dokploy

1. Mismo repo, mismo criterio de dos campos que el backend:
   - **Dockerfile Path:** `frontend/Dockerfile`
   - **Docker Context Path:** `frontend`
2. Dominio: `macacha.saltia.com.ar`.
3. **Importante:** Next.js inlinea las variables `NEXT_PUBLIC_*` en el
   bundle del browser durante el build, no en runtime — no alcanza con
   cargarla en las variables de entorno normales. En la pestaña
   **Environment** de la Application, además del cuadro normal de
   variables de runtime hay un cuadro separado llamado **"Build Time
   Arguments"** (recibido por el `Dockerfile` vía `ARG
   NEXT_PUBLIC_API_URL`). Ahí es donde va:

   ```
   NEXT_PUBLIC_API_URL=https://api.macacha.saltia.com.ar
   ```

   Si más adelante cambiás este valor, hace falta un **rebuild** de la
   Application (no alcanza con un restart o un redeploy sin rebuild).

4. Activar auto-deploy en push a `main`.

## 6. DNS

En el DNS de `saltia.com.ar`, crear (A record a la IP del servidor, o
CNAME si Dokploy da un hostname):

- `macacha.saltia.com.ar`
- `api.macacha.saltia.com.ar`

Dokploy emite el certificado SSL solo, una vez que el dominio resuelve.

## 7. Crear el usuario admin de producción

Una vez el backend está corriendo, crear el primer admin (mismo comando
que en local, apuntando a la base de producción):

```bash
cd backend
DATABASE_URL="<connection-string-de-produccion>" python -m agent.admin.create_admin admin@macacha.gob.ar
```

## 8. Ingesta de los trámites

`backend/db/schema.sql` solo crea las tablas — no carga ningún trámite.
Corré la ingesta contra la base de producción con el archivo JSON de
trámites que ya tenés (reemplazá `<ruta-al-archivo>`):

```bash
cd backend
DATABASE_URL="<connection-string-de-produccion>" python -m ingest.load <ruta-al-archivo>
```

Es idempotente — se puede volver a correr sin duplicar datos ni volver a
llamar a la API de embeddings si el contenido no cambió.

## 9. Verificación final

- [ ] `https://api.macacha.saltia.com.ar/docs` responde 200 con candado SSL válido.
- [ ] `https://macacha.saltia.com.ar` carga el chat con candado SSL válido.
- [ ] Login de admin funciona (`/admin/login` con el usuario del paso 7).
- [ ] Un mensaje de chat de prueba responde y el panel derecho muestra el top 3 o la info del trámite.
- [ ] Un commit trivial pusheado a `main` dispara un redeploy automático en ambas Applications.
