# Deploy en Dokploy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dejar el repo listo para desplegar en Dokploy — Dockerfiles de backend y frontend verificados con builds locales, housekeeping de git (rama `main`, `.gitignore`), y un runbook con los pasos manuales (Dokploy, DNS, push) que quedan fuera del alcance de este plan porque requieren acceso a sistemas externos (panel de Dokploy, registrador de DNS, GitHub).

**Architecture:** Dos Dockerfiles nuevos (uno por servicio), sin tocar código de aplicación. Cada uno se verifica con `docker build` + `docker run` + `curl` local — no hay lógica de negocio nueva, así que no hay tests de pytest/vitest que agregar; la "prueba" de cada task es que la imagen compila y el contenedor sirve una respuesta.

**Tech Stack:** Docker (ya disponible en este entorno — `docker --version` confirmado), Python 3.12-slim, Node 20-slim.

## Global Constraints

- Dominios: frontend `macacha.saltia.com.ar`, backend `api.macacha.saltia.com.ar` (del spec).
- `FRONTEND_ORIGIN` para el backend en producción: `https://macacha.saltia.com.ar` (documentar en el runbook, no hardcodear en código — ya se lee de env var).
- `NEXT_PUBLIC_API_URL` para el frontend en producción: `https://api.macacha.saltia.com.ar`.
- No usar `output: "standalone"` en `next.config.ts` (no está configurado hoy, no se agrega).
- `frontend/public/` no existe hoy — el Dockerfile del frontend no copia esa carpeta.
- El push a GitHub (`https://github.com/sebamasaguer/macacha.git`, rama `main`) lo hace el usuario manualmente — ninguna task de este plan ejecuta `git push`.
- Postgres de producción es gestionado por Dokploy (imagen `pgvector/pgvector:pg16`), no el `docker-compose.yml` local — ese archivo no se toca.

---

## Task 1: Housekeeping de git (rama `main` + `.gitignore`)

**Files:**
- Modify: `.gitignore`

**Interfaces:**
- Ninguna — no hay código productivo en esta task.

- [ ] **Step 1: Agregar `backend/.venv/` a `.gitignore`**

En `.gitignore`, agregar una línea `backend/.venv/` (después de las líneas de `backend/__pycache__/`):

```
.superpowers/
backend/__pycache__/
backend/**/__pycache__/
backend/.venv/
*.pyc
.env
frontend/node_modules/
frontend/.next/
frontend/.env.local
frontend/tsconfig.tsbuildinfo
```

- [ ] **Step 2: Confirmar que `backend/.venv/` ya no aparece como sin trackear**

Run: `git status --short`
Expected: `backend/.venv/` no aparece en la salida (antes aparecía como `??`).

- [ ] **Step 3: Renombrar la rama local `master` a `main`**

Run: `git branch --show-current` (confirmar que estás en `master` antes de renombrar)

```bash
git branch -m master main
```

- [ ] **Step 4: Verificar la rama**

Run: `git branch --show-current`
Expected: `main`

- [ ] **Step 5: Commit**

```bash
git add .gitignore
git commit -m "chore: ignorar backend/.venv/ y preparar la rama main para el deploy"
```

(El rename de rama no genera un commit propio — es un cambio de referencia local, se refleja solo cuando el usuario haga `git push -u origin main`.)

---

## Task 2: Dockerfile del backend

**Files:**
- Create: `backend/Dockerfile`
- Create: `backend/.dockerignore`

**Interfaces:**
- Produces: imagen Docker que expone el puerto `8000` y corre `uvicorn agent.api:app`.

- [ ] **Step 1: Crear `backend/.dockerignore`**

```
.venv/
__pycache__/
**/__pycache__/
.pytest_cache/
tests/
.env
```

- [ ] **Step 2: Crear `backend/Dockerfile`**

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "agent.api:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 3: Build de la imagen**

Run: `cd /home/seba/Escritorio/workspace/macacha && docker build -t macacha-backend -f backend/Dockerfile backend`
Expected: build termina con `Successfully tagged macacha-backend:latest` (o el mensaje equivalente de BuildKit), sin errores.

- [ ] **Step 4: Levantar el contenedor y verificar que responde**

El endpoint `/docs` no toca la base de datos (el pool de conexión es lazy, vía `@lru_cache`), así que alcanza con variables de entorno dummy para confirmar que la app arranca:

```bash
docker run -d --name macacha-backend-test -p 8001:8000 \
  -e ADMIN_JWT_SECRET=test-secret-para-verificar-build \
  -e DATABASE_URL=postgresql://fake:fake@localhost:5432/fake \
  -e OPENAI_API_KEY=sk-fake \
  macacha-backend

sleep 2
curl -sS -o /dev/null -w "%{http_code}\n" http://localhost:8001/docs
```

Expected: `200`.

- [ ] **Step 5: Limpiar el contenedor de prueba**

```bash
docker stop macacha-backend-test && docker rm macacha-backend-test
```

- [ ] **Step 6: Commit**

```bash
git add backend/Dockerfile backend/.dockerignore
git commit -m "feat: agregar Dockerfile del backend para el deploy en Dokploy"
```

---

## Task 3: Dockerfile del frontend

**Files:**
- Create: `frontend/Dockerfile`
- Create: `frontend/.dockerignore`

**Interfaces:**
- Produces: imagen Docker que expone el puerto `3000` y corre `npm start` (Next.js en modo producción).

- [ ] **Step 1: Crear `frontend/.dockerignore`**

```
node_modules/
.next/
.env.local
```

- [ ] **Step 2: Crear `frontend/Dockerfile`**

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

- [ ] **Step 3: Build de la imagen**

Run: `cd /home/seba/Escritorio/workspace/macacha && docker build -t macacha-frontend -f frontend/Dockerfile frontend`
Expected: build termina sin errores. `npm run build` corre dentro del stage `builder` — si hay algún error de compilación de Next.js/TypeScript, el build de Docker falla ahí (misma señal que `npx tsc --noEmit` localmente).

- [ ] **Step 4: Levantar el contenedor y verificar que responde**

```bash
docker run -d --name macacha-frontend-test -p 3001:3000 \
  -e NEXT_PUBLIC_API_URL=http://localhost:8001 \
  macacha-frontend

sleep 3
curl -sS -o /dev/null -w "%{http_code}\n" http://localhost:3001
```

Expected: `200`.

- [ ] **Step 5: Limpiar el contenedor de prueba**

```bash
docker stop macacha-frontend-test && docker rm macacha-frontend-test
```

- [ ] **Step 6: Commit**

```bash
git add frontend/Dockerfile frontend/.dockerignore
git commit -m "feat: agregar Dockerfile del frontend para el deploy en Dokploy"
```

---

## Task 4: Runbook de deploy en Dokploy

**Files:**
- Create: `docs/deploy-dokploy.md`

**Interfaces:**
- Ninguna — es documentación para el usuario, no código.

- [ ] **Step 1: Escribir el runbook**

Crear `docs/deploy-dokploy.md` con este contenido exacto. Nota: dentro
del bloque de abajo, las secuencias `\`\`\`` (con barra invertida) son
un escape para que este bloque no se corte a sí mismo — en el archivo
real `docs/deploy-dokploy.md` van comillas invertidas triples normales,
sin la barra invertida.

```markdown
# Deploy de Macacha en Dokploy

Checklist para llevar Macacha a producción. Dokploy ya está instalado y
corriendo en el servidor. Ver el diseño completo en
`docs/superpowers/specs/2026-07-30-deploy-dokploy-design.md`.

## 1. Generar el secreto de producción

`ADMIN_JWT_SECRET` de producción tiene que ser distinto al de desarrollo:

\`\`\`bash
openssl rand -hex 32
\`\`\`

Guardá el resultado — se usa en el paso 3.

## 2. Crear la Database en Dokploy

1. En el proyecto de Dokploy, crear un recurso **Database** → Postgres.
2. Imagen: `pgvector/pgvector:pg16` (no la imagen default de Postgres —
   necesita la extensión pgvector).
3. Una vez creada, copiar la connection string interna que da Dokploy
   (la vas a necesitar en el paso 3).
4. Aplicar el esquema una sola vez, desde tu máquina (necesita conexión
   de red hacia la base — Dokploy suele tener una opción para exponer el
   puerto temporalmente):

   \`\`\`bash
   psql "<connection-string-de-produccion>" -f backend/db/schema.sql
   \`\`\`

## 3. Push a GitHub

\`\`\`bash
git push -u origin main
\`\`\`

## 4. Crear la Application del backend en Dokploy

1. Conectar Dokploy al repo `https://github.com/sebamasaguer/macacha.git`.
2. Tipo: Application, build desde Dockerfile.
3. Path del contexto de build / subcarpeta: `backend/`.
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

1. Mismo repo, subcarpeta `frontend/`.
2. Dominio: `macacha.saltia.com.ar`.
3. Variable de entorno:

   | Variable | Valor |
   |---|---|
   | `NEXT_PUBLIC_API_URL` | `https://api.macacha.saltia.com.ar` |

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

\`\`\`bash
cd backend
DATABASE_URL="<connection-string-de-produccion>" python -m agent.admin.create_admin admin@macacha.gob.ar
\`\`\`

## 8. Verificación final

- [ ] `https://api.macacha.saltia.com.ar/docs` responde 200 con candado SSL válido.
- [ ] `https://macacha.saltia.com.ar` carga el chat con candado SSL válido.
- [ ] Login de admin funciona (`/admin/login` con el usuario del paso 7).
- [ ] Un mensaje de chat de prueba responde y el panel derecho muestra el top 3 o la info del trámite.
- [ ] Un commit trivial pusheado a `main` dispara un redeploy automático en ambas Applications.
```

- [ ] **Step 2: Self-review de lectura**

Releer el archivo creado y confirmar que cada comando tiene los valores
reales del proyecto (dominios, URL del repo) y no placeholders genéricos
como `<tu-dominio>`.

- [ ] **Step 3: Commit**

```bash
git add docs/deploy-dokploy.md
git commit -m "docs: runbook de deploy en Dokploy"
```

---

## Self-Review Checklist (ya aplicado al escribir este plan)

- **Cobertura del spec:** Dockerfiles (Tasks 2-3), esquema de base y
  variables de entorno documentadas en el runbook (Task 4), housekeeping
  de git (Task 1). El push, la creación de recursos en Dokploy y el DNS
  quedan como pasos manuales del runbook — no son automatizables desde
  este entorno (sin credenciales de git, sin acceso al panel de Dokploy
  ni al DNS del usuario), tal como se acordó en el diseño.
- **Sin placeholders:** todos los pasos tienen comandos y contenido
  completo, sin "TODO" ni "completar después". El runbook usa los
  dominios y la URL del repo reales acordados en el diseño.
- **Consistencia:** los nombres de dominio, variables de entorno y rutas
  de Dockerfile son los mismos en el spec, el plan y el runbook.

## Después de este plan

Cuando las 4 tasks estén completas y revisadas, el trabajo automatizable
termina ahí. Los pasos del runbook (`docs/deploy-dokploy.md`) los ejecuta
el usuario a mano, fuera de este plan.
