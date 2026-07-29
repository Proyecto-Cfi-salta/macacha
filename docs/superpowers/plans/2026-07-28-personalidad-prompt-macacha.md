# Personalidad y estilo del prompt (sub-proyecto A) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reemplazar `SYSTEM_PROMPT` en `backend/agent/orchestrator.py` para que el chat responda en prosa natural por default, sin cierres repetidos, reconociendo frustración/confusión del usuario, y sin emojis.

**Architecture:** Cambio de un solo string constante en un solo archivo. No hay lógica nueva, no hay tests automatizados posibles (el prompt no tiene comportamiento verificable por unit test) — la verificación es manual, conversando con el chat real.

**Tech Stack:** Python (backend existente, sin dependencias nuevas).

## Global Constraints

- El nuevo `SYSTEM_PROMPT` debe ser exactamente el texto aprobado en el spec `docs/superpowers/specs/2026-07-28-personalidad-prompt-macacha-design.md` — no parafrasear ni resumir.
- No tocar ninguna otra parte de `orchestrator.py` (lógica de tool calling, desambiguación, `_armar_fuentes`, etc.) — el cambio es exclusivamente el string de `SYSTEM_PROMPT`.
- No agregar tests automatizados para el contenido del prompt (no hay comportamiento determinístico que testear; sería un test frágil contra output de LLM).

---

### Task 1: Reemplazar el `SYSTEM_PROMPT`

**Files:**
- Modify: `backend/agent/orchestrator.py:7-21`

**Interfaces:**
- Consumes: nada nuevo.
- Produces: `SYSTEM_PROMPT` (mismo nombre, mismo tipo `str`, mismo uso en `orchestrator.py:33`) — no cambia la interfaz, solo el contenido.

- [ ] **Step 1: Reemplazar el bloque `SYSTEM_PROMPT`**

Reemplazar las líneas 7-21 de `backend/agent/orchestrator.py` (el bloque completo `SYSTEM_PROMPT = (...)`) por:

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
    "de ignorarlo. No uses emojis. Sin perder precisión: respondé siempre "
    "basándote únicamente en la información que te devuelven las herramientas "
    "disponibles, nunca inventes requisitos, costos, pasos ni plazos. Si la "
    "herramienta buscar_tramite devuelve varios trámites candidatos y no está "
    "claro cuál necesita la persona, preguntá con calidez para desambiguar "
    "antes de usar las demás herramientas. Cuando menciones un trámite, usá su "
    "nombre oficial y, si corresponde, su enlace oficial."
)
```

El resto del archivo (`MAX_ITERACIONES_TOOLS`, `procesar_turno`, `_emitir_respuesta_trozeada`, `_armar_fuentes`) queda sin cambios.

- [ ] **Step 2: Correr la suite completa de tests para confirmar que nada se rompió**

Run: `cd backend && source .venv/bin/activate && pytest -q`
Expected: todos los tests pasan (mismo resultado que antes del cambio — no hay tests que dependan del contenido literal del prompt).

- [ ] **Step 3: Commit**

```bash
git add backend/agent/orchestrator.py
git commit -m "feat: prosa natural y sin cierres repetidos en el tono del chat"
```

---

### Task 2: Verificación manual

**Files:** ninguno (solo verificación, sin cambios de código).

**Interfaces:**
- Consumes: backend real corriendo (`uvicorn`) con `OPENAI_API_KEY` válida, endpoint `POST /chat`.
- Produces: confirmación de los criterios de aceptación del spec.

- [ ] **Step 1: Confirmar prosa por default con pocos ítems**

`RC-0004` ("Seguimiento, Validación y Descarga de Actas") tiene un solo
requisito en el snapshot vigente — caso claro para confirmar que no arma
una lista de un solo ítem.

Run:
```bash
SESSION_ID=$(python3 -c "import uuid; print(uuid.uuid4())")
curl -s -N -m 30 -X POST http://localhost:8000/chat -H "Content-Type: application/json" \
  -d "{\"session_id\":\"$SESSION_ID\",\"mensaje\":\"qué necesito para hacer el seguimiento y descarga de mi acta\"}"
```

Expected: la respuesta explica los requisitos en oraciones seguidas, no como lista numerada/viñetas (a menos que el trámite realmente tenga más de 4 ítems).

- [ ] **Step 2: Confirmar que no repite el mismo cierre en la misma conversación**

Usando la misma `SESSION_ID` del paso anterior, mandar un segundo mensaje seguido (ej. "¿y cuánto tarda?").

Run:
```bash
curl -s -N -m 30 -X POST http://localhost:8000/chat -H "Content-Type: application/json" \
  -d "{\"session_id\":\"$SESSION_ID\",\"mensaje\":\"¿y cuánto tarda?\"}"
```

Expected: si ambas respuestas cierran con una pregunta, no es la misma pregunta/frase textual en las dos.

- [ ] **Step 3: Confirmar reconocimiento de frustración**

Nueva sesión, mandar un mensaje expresando frustración/confusión explícita.

Run:
```bash
SESSION_ID_2=$(python3 -c "import uuid; print(uuid.uuid4())")
curl -s -N -m 30 -X POST http://localhost:8000/chat -H "Content-Type: application/json" \
  -d "{\"session_id\":\"$SESSION_ID_2\",\"mensaje\":\"no entiendo nada de cómo hacer una denuncia de consumidor, es un embole\"}"
```

Expected: la respuesta reconoce explícitamente la frustración/confusión antes o junto con dar la información (no la ignora y arranca directo con datos).

- [ ] **Step 4: Confirmar ausencia de emojis**

Revisar las respuestas de los tres pasos anteriores: ninguna debe contener emojis.

- [ ] **Step 5: Reportar resultado**

Si los 4 criterios se cumplen, marcar la tarea como completa. Si alguno falla de forma consistente (ej. sigue repitiendo el mismo cierre en 2-3 intentos), documentar el ejemplo concreto y decidir si el prompt necesita un ajuste adicional antes de dar por cerrado el sub-proyecto A.
