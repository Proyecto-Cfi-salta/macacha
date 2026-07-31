# Macacha — Deploy en servidor propio con Dokploy

## Contexto

Hasta ahora el proyecto solo corría en local: `docker-compose.yml` levanta
únicamente Postgres, y backend/frontend se ejecutaban con `uvicorn` y
`next dev` directo en la máquina de desarrollo. Este documento define cómo
llevar Macacha a un servidor con [Dokploy](https://dokploy.com/) ya
instalado y corriendo.

Decisiones ya tomadas:

- **Estructura**: tres recursos separados en un proyecto de Dokploy —
  Database (Postgres gestionado), Application backend, Application
  frontend. Cada uno con su propio deploy, logs, dominio y variables de
  entorno.
- **Repo**: el código se sube a `https://github.com/sebamasaguer/macacha.git`
  (privado). Hoy este repo no tiene remoto configurado — se agrega como
  parte de este trabajo.
- **Dominios**: `macacha.saltia.com.ar` (frontend) y
  `api.macacha.saltia.com.ar` (backend).
- **Postgres**: gestionado por Dokploy (no el `docker-compose.yml` actual),
  imagen `pgvector/pgvector:pg16`.
- **Auto-deploy**: en cada push a `main` (la rama local `master` se renombra
  a `main` al pushear, siguiendo la convención actual de GitHub).

## Dockerfiles

### `backend/Dockerfile` (nuevo)

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "agent.api:app", "--host", "0.0.0.0", "--port", "8000"]
```

### `backend/.dockerignore` (nuevo)

```
.venv/
__pycache__/
**/__pycache__/
.pytest_cache/
tests/
.env
```

### `frontend/Dockerfile` (nuevo)

Build multi-stage estándar de Next.js (sin `output: "standalone"` — el
`next.config.ts` actual no lo configura y no hace falta para el tamaño de
esta app):

```dockerfile
FROM node:20-slim AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:20-slim AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:20-slim AS runner
WORKDIR /app
ENV NODE_ENV=production
COPY --from=builder /app/package.json /app/package-lock.json ./
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/next.config.ts ./

EXPOSE 3000

CMD ["npm", "start"]
```

`frontend/public/` no existe hoy en el repo, así que no hay `COPY` para
esa carpeta. Si más adelante se agrega (favicon, assets estáticos), hay
que sumar una línea `COPY --from=builder /app/public ./public` a este
stage.

### `frontend/.dockerignore` (nuevo)

```
node_modules/
.next/
.env.local
```

## Esquema de la base de datos

`backend/db/schema.sql` ya es idempotente (`CREATE TABLE IF NOT EXISTS`,
`ADD COLUMN IF NOT EXISTS` donde corresponde), pero el Postgres gestionado
de Dokploy no tiene el mecanismo `docker-entrypoint-initdb.d` que usa hoy
el `docker-compose.yml` local. Se aplica **una sola vez, a mano**, después
de crear la Database en Dokploy y antes del primer deploy del backend:

```bash
psql "$DATABASE_URL_PRODUCCION" -f backend/db/schema.sql
```

(`backend/db/init_test_db.sql` no se usa en producción — es solo para la
base de test local.)

## Variables de entorno

### Backend (Application, panel de Dokploy)

| Variable | Valor |
|---|---|
| `DATABASE_URL` | connection string interna que da Dokploy al crear la Database |
| `OPENAI_API_KEY` | key real de producción |
| `GEMINI_API_KEY` | opcional, fallback ya soportado por `ingest/openai_client.py` |
| `ADMIN_JWT_SECRET` | secreto nuevo generado para producción (no reusar el de `.env` local) |
| `FRONTEND_ORIGIN` | `https://macacha.saltia.com.ar` |

`FRONTEND_ORIGIN` ya lo lee `agent/api.py` (línea ~41) para configurar
`CORSMiddleware` — no requiere cambios de código, solo setear la variable.

### Frontend (Application, panel de Dokploy)

| Variable | Valor |
|---|---|
| `NEXT_PUBLIC_API_URL` | `https://api.macacha.saltia.com.ar` |

## DNS

Dos registros en el DNS de `saltia.com.ar` apuntando a la IP del servidor
(A record, o CNAME si Dokploy da un hostname propio):

- `macacha.saltia.com.ar`
- `api.macacha.saltia.com.ar`

Dokploy emite el certificado SSL (Let's Encrypt) automáticamente una vez
que el dominio resuelve correctamente — no requiere configuración manual
de certificados.

## Repositorio y push

Este entorno no tiene credenciales de git configuradas (sin SSH key para
GitHub, sin `gh` CLI, sin credential helper) — no se puede pushear
directo a `https://github.com/sebamasaguer/macacha.git`. El dueño del
repo debe:

- Proveer un Personal Access Token (permiso `repo`) para push por HTTPS, o
- Hacer el push inicial él mismo, una vez que la rama `main` y los
  commits estén listos localmente (`git push -u origin main`).

`.gitignore` actual no incluye `backend/.venv/` (queda como carpeta sin
trackear hoy) — se agrega como parte de esta limpieza, ya que no debe
terminar commiteada al repo público/privado.

## Configuración en Dokploy

Una vez el código está en GitHub:

1. Crear la Database (Postgres, imagen `pgvector/pgvector:pg16`) → aplicar
   `schema.sql` (sección arriba).
2. Crear la Application backend, apuntando al repo y a la subcarpeta
   `backend/` (monorepo — Dokploy soporta especificar el path del
   Dockerfile/contexto de build dentro del repo), dominio
   `api.macacha.saltia.com.ar`, variables de entorno de la tabla de
   arriba, webhook de auto-deploy en push a `main`.
3. Crear la Application frontend, apuntando a la subcarpeta `frontend/`,
   dominio `macacha.saltia.com.ar`, su variable de entorno, mismo webhook.

## Testing

- Build local de ambas imágenes Docker (`docker build -f backend/Dockerfile
  backend` y `docker build -f frontend/Dockerfile frontend`) antes de
  pushear, para confirmar que compilan sin depender del servidor.
- No hay tests automatizados nuevos — esto es infraestructura de deploy,
  no lógica de aplicación. La suite existente (pytest + vitest) no cambia.
- Verificación manual de humo contra las URLs de producción una vez que
  Dokploy termina el primer deploy: login de admin
  (`https://api.macacha.saltia.com.ar/admin/login`), un mensaje de chat de
  prueba desde `https://macacha.saltia.com.ar`, y que el panel derecho
  cargue el top 3 / info del trámite.

## Fuera de alcance

- Instalar Dokploy en el servidor (ya está instalado).
- CI (GitHub Actions) para correr la suite de tests antes del deploy —
  Dokploy despliega directo en push, sin ese paso intermedio.
- Backups automatizados de la Database más allá de lo que Dokploy ofrezca
  por defecto en su panel.
- Migrar `docker-compose.yml` local — sigue existiendo tal cual para
  desarrollo, sin relación con el Postgres de producción.
- Rotar o migrar los 32 trámites ya ingeridos — la ingesta a producción
  (`python -m ingest.load`) es un paso posterior, no cubierto acá.

## Criterios de aceptación

- `docker build` de `backend/Dockerfile` y `frontend/Dockerfile` termina
  sin errores en local.
- El código está pusheado a `main` en
  `https://github.com/sebamasaguer/macacha.git`.
- Las tres Applications/Database existen en el proyecto de Dokploy,
  correctamente configuradas.
- `https://macacha.saltia.com.ar` carga el chat y
  `https://api.macacha.saltia.com.ar/docs` responde 200, ambos con
  certificado SSL válido.
- Un push a `main` dispara un redeploy automático (verificado con un
  commit trivial).
