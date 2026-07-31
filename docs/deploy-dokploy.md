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
4. Aplicar el esquema una sola vez, desde tu máquina (necesita conexión
   de red hacia la base — Dokploy suele tener una opción para exponer el
   puerto temporalmente):

   ```bash
   psql "<connection-string-de-produccion>" -f backend/db/schema.sql
   ```

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
