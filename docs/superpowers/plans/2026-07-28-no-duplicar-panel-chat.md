# No duplicar información entre el chat y el panel (sub-proyecto C) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que el chat deje de recitar en texto los datos duros que el panel derecho ya muestra (requisitos, costo, modalidad, duración, pasos, enlaces oficiales) — respuestas breves al identificar un trámite, respuestas puntuales ante preguntas concretas.

**Architecture:** Cambio de un solo string constante (`SYSTEM_PROMPT`) en un solo archivo. Sin lógica nueva, sin tests automatizados posibles — verificación manual conversando con el chat real, mismo patrón que el sub-proyecto A.

**Tech Stack:** Python (backend existente, sin dependencias nuevas).

## Global Constraints

- El nuevo `SYSTEM_PROMPT` debe ser exactamente el texto aprobado en `docs/superpowers/specs/2026-07-28-no-duplicar-panel-chat-design.md` — no parafrasear.
- No tocar ninguna otra parte de `orchestrator.py` ni ningún otro archivo — el cambio es exclusivamente el string de `SYSTEM_PROMPT`.
- No agregar tests automatizados para el contenido del prompt.

---

### Task 1: Reemplazar el `SYSTEM_PROMPT`

**Files:**
- Modify: `backend/agent/orchestrator.py` (bloque `SYSTEM_PROMPT`)

**Interfaces:**
- Consumes: nada nuevo.
- Produces: `SYSTEM_PROMPT` (mismo nombre, mismo tipo `str`, mismo uso en `procesar_turno`) — no cambia la interfaz, solo el contenido.

- [ ] **Step 1: Reemplazar el bloque `SYSTEM_PROMPT`**

Reemplazar el bloque completo `SYSTEM_PROMPT = (...)` en `backend/agent/orchestrator.py` por:

```python
SYSTEM_PROMPT = (
    "Sos Macacha, la asistente virtual de trámites de la administración pública "
    "de la Provincia de Salta. Tu objetivo es ayudar a las personas a entender y "
    "completar sus trámites de la forma más simple posible. Sabés que muchos "
    "trámites pueden ser confusos o estresantes, así que tratá a cada persona "
    "con calidez y empatía — como alguien de confianza que se toma el trabajo en "
    "serio, no como un formulario que recita datos. Podés usar un tono cercano y "
    "humano. Contá las cosas como lo haría una persona explicándole a otra: en "
    "oraciones seguidas, no como una lista de trámite. Usá viñetas o numeración "
    "solo si hay varios ítems y de verdad ayuda a leerlos (por ejemplo, más de "
    "cuatro requisitos o pasos) — nunca como formato por defecto. Variá cómo "
    "empezás y cerrás cada respuesta: no repitas la misma pregunta de cierre en "
    "todos los mensajes. Si la persona comenta que algo le resulta tedioso, "
    "confuso o frustrante, reconocelo antes de pasar a la información, en vez "
    "de ignorarlo. No uses emojis. Además de vos, la persona tiene a la vista "
    "un panel con los datos duros del trámite (requisitos, costo, modalidad, "
    "duración, pasos y enlaces oficiales) en cuanto identificás cuál es — no "
    "hace falta que se los repitas ahí. Cuando identifiques un trámite por "
    "primera vez, respondé en una o dos oraciones (qué trámite es y, si suma, "
    "algún dato saliente como si es gratuito o rápido) e invitá a mirar el "
    "panel o a preguntar algo puntual — no listes requisitos, pasos ni "
    "enlaces en el chat. Si te preguntan algo puntual, como el costo o una "
    "duda sobre una sección específica, respondé ese punto concreto con la "
    "información de las herramientas, sin repetir el resto de los datos que "
    "ya tiene a la vista. Sin perder precisión: respondé siempre basándote "
    "únicamente en la información que te devuelven las herramientas "
    "disponibles, nunca inventes requisitos, costos, pasos ni plazos. Si la "
    "herramienta buscar_tramite devuelve varios trámites candidatos y no está "
    "claro cuál necesita la persona, preguntá con calidez para desambiguar "
    "antes de usar las demás herramientas. Cuando menciones un trámite, usá su "
    "nombre oficial."
)
```

El resto del archivo (`MAX_ITERACIONES_TOOLS`, `procesar_turno`, `_armar_fuentes`) queda sin cambios.

- [ ] **Step 2: Correr la suite completa de tests para confirmar que nada se rompió**

Run: `cd backend && source .venv/bin/activate && pytest -q`
Expected: todos los tests pasan (mismo resultado que antes del cambio — ningún test depende del contenido literal del prompt).

- [ ] **Step 3: Commit**

```bash
git add backend/agent/orchestrator.py
git commit -m "feat: evitar que el chat repita en texto los datos que ya muestra el panel"
```

---

### Task 2: Verificación manual

**Files:** ninguno (solo verificación).

**Interfaces:**
- Consumes: backend real corriendo, endpoint `POST /chat`.

- [ ] **Step 1: Confirmar respuesta breve al identificar un trámite**

Run:
```bash
SESSION_ID=$(python3 -c "import uuid; print(uuid.uuid4())")
curl -s -N -m 30 -X POST http://localhost:8000/chat -H "Content-Type: application/json" \
  -d "{\"session_id\":\"$SESSION_ID\",\"mensaje\":\"qué necesito para hacer el seguimiento y descarga de mi acta\"}"
```
Expected: la respuesta identifica el trámite (RC-0004, "Seguimiento, Validación y Descarga de Actas") en 1-2 oraciones, sin listar requisitos, pasos ni enlaces — invita a mirar el panel o preguntar algo puntual.

- [ ] **Step 2: Confirmar respuesta puntual ante una pregunta concreta**

Usando la misma `SESSION_ID` del paso anterior:

Run:
```bash
curl -s -N -m 30 -X POST http://localhost:8000/chat -H "Content-Type: application/json" \
  -d "{\"session_id\":\"$SESSION_ID\",\"mensaje\":\"¿y cuánto sale?\"}"
```
Expected: responde el costo puntual (este trámite no tiene costo) sin repetir modalidad, duración, pasos ni enlaces.

- [ ] **Step 3: Confirmar que un mensaje tipo botón-de-dudas elabora, no remite genéricamente al panel**

Nueva sesión, simulando el mensaje que manda el botón "¿Tenés dudas?" de la sección Pasos:

Run:
```bash
SESSION_ID_2=$(python3 -c "import uuid; print(uuid.uuid4())")
curl -s -N -m 30 -X POST http://localhost:8000/chat -H "Content-Type: application/json" \
  -d "{\"session_id\":\"$SESSION_ID_2\",\"mensaje\":\"Tengo una duda sobre los pasos de Seguimiento, Validación y Descarga de Actas.\"}"
```
Expected: la respuesta elabora sobre los pasos de ese trámite (ej. detalla o aclara el proceso), no responde solamente algo genérico como "podés verlos en el panel de al lado".

- [ ] **Step 4: Reportar resultado**

Si los 3 criterios se cumplen, marcar la tarea como completa. Si alguno falla de forma consistente, documentar el ejemplo concreto y decidir si el prompt necesita un ajuste adicional.
