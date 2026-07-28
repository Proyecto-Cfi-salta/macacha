# Tono cálido del chat + panel de datos duros — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ajustar el tono del `SYSTEM_PROMPT` del agente para que sea cálido y empático (sin mencionar organismos específicos, para que no se desactualice), y extender el panel derecho del chat con costo, modalidad, duración, pasos y enlaces oficiales, según el spec aprobado en `docs/superpowers/specs/2026-07-27-tono-calido-y-panel-datos-duros-design.md`.

**Architecture:** Cambio de constante en `agent/orchestrator.py` (sin lógica nueva). Extensión de un endpoint público ya existente (`GET /tramites/{id}`) con 5 campos más del mismo snapshot que ya lee. Extensión del tipo TypeScript correspondiente y del componente de presentación `TramiteInfoPanel.tsx` con 3 secciones condicionales nuevas, mismo patrón visual que las secciones ya existentes.

**Tech Stack:** Sin dependencias nuevas.

## Global Constraints

- Identificadores en español, sin comentarios salvo WHY no obvio.
- El `SYSTEM_PROMPT` no debe mencionar ningún organismo específico (evita que se desactualice cada vez que se cargan datos de un organismo nuevo).
- Cada sección nueva del panel derecho es condicional: solo se muestra si el dato correspondiente no viene vacío — mismo patrón que ya usan las secciones de Requisitos y Contacto.
- Sin tests automatizados para el texto del prompt ni para el componente de panel (mismo criterio ya establecido en el proyecto: sin `jsdom`/`@testing-library`, y un string constante no tiene lógica que testear).

---

## Backend

### Task 1: `SYSTEM_PROMPT` — tono cálido y sin organismo hardcodeado

**Files:**
- Modify: `backend/agent/orchestrator.py`

**Interfaces:** ninguna (cambio de una constante de texto, sin cambios de firma).

- [ ] **Step 1: Reemplazar el `SYSTEM_PROMPT`**

En `backend/agent/orchestrator.py`, reemplazar:

```python
SYSTEM_PROMPT = (
    "Sos Macacha, la asistente virtual de trámites de la administración pública "
    "de la Provincia de Salta. Hoy tenés información sobre trámites del Registro "
    "Civil. Respondé siempre basándote únicamente en la información que te "
    "devuelven las herramientas disponibles: nunca inventes requisitos, costos, "
    "pasos ni plazos. Si la herramienta buscar_tramite devuelve varios trámites "
    "candidatos y no está claro cuál necesita el usuario, preguntá para "
    "desambiguar antes de usar las demás herramientas. Cuando menciones un "
    "trámite, usá su nombre oficial y, si corresponde, su enlace oficial."
)
```

por:

```python
SYSTEM_PROMPT = (
    "Sos Macacha, la asistente virtual de trámites de la administración pública "
    "de la Provincia de Salta. Tu objetivo es ayudar a las personas a entender y "
    "completar sus trámites de la forma más simple posible. Sabés que muchos "
    "trámites pueden ser confusos o estresantes, así que tratá a cada persona "
    "con calidez y empatía — como alguien de confianza que se toma el trabajo en "
    "serio, no como un formulario que recita datos. Podés usar un tono cercano y "
    "humano, pero sin perder precisión: respondé siempre basándote únicamente en "
    "la información que te devuelven las herramientas disponibles, nunca "
    "inventes requisitos, costos, pasos ni plazos. Si la herramienta "
    "buscar_tramite devuelve varios trámites candidatos y no está claro cuál "
    "necesita la persona, preguntá con calidez para desambiguar antes de usar "
    "las demás herramientas. Cuando menciones un trámite, usá su nombre oficial "
    "y, si corresponde, su enlace oficial."
)
```

- [ ] **Step 2: Correr la suite completa para confirmar que nada se rompió**

Run: `cd backend && source .venv/bin/activate && pytest -q`
Expected: PASS (ningún test depende del texto exacto del `SYSTEM_PROMPT`)

- [ ] **Step 3: Commit**

```bash
git add backend/agent/orchestrator.py
git commit -m "feat: tono cálido en el system prompt del agente"
```

---

### Task 2: `GET /tramites/{id}` — sumar costo, modalidad, duración, pasos, enlaces oficiales

**Files:**
- Modify: `backend/agent/api.py`
- Modify: `backend/tests/test_api.py`

**Interfaces:**
- Produces: `GET /tramites/{tramite_id}` devuelve, además de los campos existentes, `costo: str`, `modalidad: str`, `duracion: str`, `pasos: list[str]`, `enlaces_oficiales: list[str]` (todos con default vacío si el snapshot no los tiene). Consumido por Task 3 (frontend).

- [ ] **Step 1: Actualizar el test existente y agregar el de defaults**

En `backend/tests/test_api.py`, reemplazar `test_get_tramite_devuelve_detalle`:

```python
def test_get_tramite_devuelve_detalle(db_conn, clean_db):
    organismo_id = repo.upsert_organismo(db_conn, "Registro Civil")
    repo.upsert_tramite(db_conn, "RC-0001", organismo_id, "Actas", "Actas Regulares")
    snapshot = {
        "id": "RC-0001",
        "organismo": "Registro Civil",
        "categoria": "Actas",
        "nombre_oficial": "Actas Regulares",
        "requisitos": ["DNI"],
        "costo": "Gratuito",
        "modalidad": "Online",
        "duracion": "10 días",
        "pasos": ["Paso 1", "Paso 2"],
        "enlaces_oficiales": ["https://registrocivilsalta.gob.ar/"],
        "telefono_contacto": "0387-4234567",
        "email_contacto": "registrocivil@salta.gob.ar",
    }
    chunks = [{"tipo_chunk": "descripcion", "texto": "texto", "fuente_url": None}]
    embeddings = [[0.0] * 1536]
    repo.insert_version_with_chunks(db_conn, "RC-0001", 1, "hash-1", snapshot, chunks, embeddings)
    db_conn.commit()

    api.app.dependency_overrides[obtener_pool] = lambda: _FakePool(db_conn)
    client = TestClient(api.app)
    try:
        respuesta = client.get("/tramites/RC-0001")
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.status_code == 200
    assert respuesta.json() == {
        "tramite_id": "RC-0001",
        "nombre_oficial": "Actas Regulares",
        "organismo": "Registro Civil",
        "categoria": "Actas",
        "requisitos": ["DNI"],
        "costo": "Gratuito",
        "modalidad": "Online",
        "duracion": "10 días",
        "pasos": ["Paso 1", "Paso 2"],
        "enlaces_oficiales": ["https://registrocivilsalta.gob.ar/"],
        "telefono_contacto": "0387-4234567",
        "email_contacto": "registrocivil@salta.gob.ar",
    }
```

Agregar a continuación (nuevo test):

```python
def test_get_tramite_sin_campos_opcionales_devuelve_defaults(db_conn, clean_db):
    organismo_id = repo.upsert_organismo(db_conn, "Registro Civil")
    repo.upsert_tramite(db_conn, "RC-0001", organismo_id, "Actas", "Actas Regulares")
    snapshot = {
        "id": "RC-0001",
        "organismo": "Registro Civil",
        "categoria": "Actas",
        "nombre_oficial": "Actas Regulares",
    }
    chunks = [{"tipo_chunk": "descripcion", "texto": "texto", "fuente_url": None}]
    embeddings = [[0.0] * 1536]
    repo.insert_version_with_chunks(db_conn, "RC-0001", 1, "hash-1", snapshot, chunks, embeddings)
    db_conn.commit()

    api.app.dependency_overrides[obtener_pool] = lambda: _FakePool(db_conn)
    client = TestClient(api.app)
    try:
        respuesta = client.get("/tramites/RC-0001")
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["requisitos"] == []
    assert cuerpo["costo"] == ""
    assert cuerpo["modalidad"] == ""
    assert cuerpo["duracion"] == ""
    assert cuerpo["pasos"] == []
    assert cuerpo["enlaces_oficiales"] == []
```

- [ ] **Step 2: Correr los tests y verificar que fallan**

Run: `cd backend && source .venv/bin/activate && pytest tests/test_api.py -v -k get_tramite`
Expected: FAIL — `test_get_tramite_devuelve_detalle` falla porque la respuesta real no incluye los campos nuevos que ahora exige el assert; `test_get_tramite_sin_campos_opcionales_devuelve_defaults` falla con `KeyError` al acceder a `cuerpo["costo"]` (no está en la respuesta actual)

- [ ] **Step 3: Extender el endpoint**

En `backend/agent/api.py`, `obtener_tramite` pasa de:

```python
@app.get("/tramites/{tramite_id}")
def obtener_tramite(tramite_id: str, pool=Depends(obtener_pool)):
    with pool.connection() as conn:
        snapshot = obtener_snapshot_vigente(conn, tramite_id)
        if snapshot is None:
            raise HTTPException(status_code=404, detail="Trámite no encontrado")
        return {
            "tramite_id": tramite_id,
            "nombre_oficial": snapshot["nombre_oficial"],
            "organismo": snapshot["organismo"],
            "categoria": snapshot["categoria"],
            "requisitos": snapshot.get("requisitos", []),
            "telefono_contacto": snapshot.get("telefono_contacto", ""),
            "email_contacto": snapshot.get("email_contacto", ""),
        }
```

a:

```python
@app.get("/tramites/{tramite_id}")
def obtener_tramite(tramite_id: str, pool=Depends(obtener_pool)):
    with pool.connection() as conn:
        snapshot = obtener_snapshot_vigente(conn, tramite_id)
        if snapshot is None:
            raise HTTPException(status_code=404, detail="Trámite no encontrado")
        return {
            "tramite_id": tramite_id,
            "nombre_oficial": snapshot["nombre_oficial"],
            "organismo": snapshot["organismo"],
            "categoria": snapshot["categoria"],
            "requisitos": snapshot.get("requisitos", []),
            "costo": snapshot.get("costo", ""),
            "modalidad": snapshot.get("modalidad", ""),
            "duracion": snapshot.get("duracion", ""),
            "pasos": snapshot.get("pasos", []),
            "enlaces_oficiales": snapshot.get("enlaces_oficiales", []),
            "telefono_contacto": snapshot.get("telefono_contacto", ""),
            "email_contacto": snapshot.get("email_contacto", ""),
        }
```

- [ ] **Step 4: Correr los tests y verificar que pasan**

Run: `cd backend && source .venv/bin/activate && pytest tests/test_api.py -v`
Expected: PASS (toda la suite del archivo)

- [ ] **Step 5: Correr la suite completa del backend**

Run: `cd backend && source .venv/bin/activate && pytest -q`
Expected: PASS (sin regresiones)

- [ ] **Step 6: Commit**

```bash
git add backend/agent/api.py backend/tests/test_api.py
git commit -m "feat: sumar costo, modalidad, duración, pasos y enlaces al endpoint público de trámite"
```

---

## Frontend

### Task 3: Panel derecho — mostrar los datos nuevos

**Files:**
- Modify: `frontend/lib/api.ts`
- Modify: `frontend/components/TramiteInfoPanel.tsx`

**Interfaces:**
- Consumes: los 5 campos nuevos que ahora devuelve `GET /tramites/{id}` (Task 2).

No hay test automatizado (componente de presentación sin lógica pura, mismo criterio que el resto del proyecto).

- [ ] **Step 1: Extender el tipo `TramiteDetalle`**

En `frontend/lib/api.ts`, el tipo pasa de:

```typescript
export type TramiteDetalle = {
  tramite_id: string;
  nombre_oficial: string;
  organismo: string;
  categoria: string;
  requisitos: string[];
  telefono_contacto: string;
  email_contacto: string;
};
```

a:

```typescript
export type TramiteDetalle = {
  tramite_id: string;
  nombre_oficial: string;
  organismo: string;
  categoria: string;
  requisitos: string[];
  costo: string;
  modalidad: string;
  duracion: string;
  pasos: string[];
  enlaces_oficiales: string[];
  telefono_contacto: string;
  email_contacto: string;
};
```

- [ ] **Step 2: Agregar las secciones nuevas al panel**

Reemplazar `frontend/components/TramiteInfoPanel.tsx` completo:

```tsx
import type { TramiteDetalle } from "../lib/api";

export function TramiteInfoPanel({ tramite }: { tramite: TramiteDetalle | null }) {
  if (!tramite) {
    return (
      <p className="text-sm text-gray-400">
        La info del trámite va a aparecer acá.
      </p>
    );
  }

  return (
    <div>
      <h2 className="font-semibold">{tramite.nombre_oficial}</h2>
      <p className="text-sm text-gray-500">{tramite.organismo}</p>

      {tramite.requisitos.length > 0 && (
        <div className="mt-4">
          <h3 className="text-sm font-medium">Requisitos</h3>
          <ul className="mt-1 list-disc pl-5 text-sm">
            {tramite.requisitos.map((requisito) => (
              <li key={requisito}>{requisito}</li>
            ))}
          </ul>
        </div>
      )}

      {(tramite.costo || tramite.modalidad || tramite.duracion) && (
        <div className="mt-4 text-sm">
          <h3 className="font-medium">Costo, modalidad y duración</h3>
          {tramite.costo && <p>Costo: {tramite.costo}</p>}
          {tramite.modalidad && <p>Modalidad: {tramite.modalidad}</p>}
          {tramite.duracion && <p>Duración: {tramite.duracion}</p>}
        </div>
      )}

      {tramite.pasos.length > 0 && (
        <div className="mt-4">
          <h3 className="text-sm font-medium">Pasos</h3>
          <ol className="mt-1 list-decimal pl-5 text-sm">
            {tramite.pasos.map((paso) => (
              <li key={paso}>{paso}</li>
            ))}
          </ol>
        </div>
      )}

      {tramite.enlaces_oficiales.length > 0 && (
        <div className="mt-4">
          <h3 className="text-sm font-medium">Enlaces oficiales</h3>
          <ul className="mt-1 list-disc pl-5 text-sm">
            {tramite.enlaces_oficiales.map((enlace) => (
              <li key={enlace}>
                <a
                  href={enlace}
                  target="_blank"
                  rel="noreferrer"
                  className="text-blue-700 underline"
                >
                  {enlace}
                </a>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="mt-4 text-sm">
        <h3 className="font-medium">Contacto</h3>
        {tramite.telefono_contacto && <p>Tel: {tramite.telefono_contacto}</p>}
        {tramite.email_contacto && <p>Mail: {tramite.email_contacto}</p>}
        {!tramite.telefono_contacto && !tramite.email_contacto && (
          <p className="text-gray-400">Sin datos de contacto.</p>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Verificar que compila**

Run: `cd frontend && npx tsc --noEmit`
Expected: sin errores nuevos

- [ ] **Step 4: Commit**

```bash
git add frontend/lib/api.ts frontend/components/TramiteInfoPanel.tsx
git commit -m "feat: mostrar costo, modalidad, duración, pasos y enlaces en el panel del trámite"
```

---

### Task 4: Verificación manual

**Files:** ninguno (solo verificación).

- [ ] **Step 1: Confirmar el tono del chat con una pregunta real**

Con el backend corriendo (recoge el cambio de `SYSTEM_PROMPT` automáticamente vía `--reload`), preguntar algo simple en `http://localhost:3000` (ej. "hola" o "¿qué necesito para un acta de nacimiento?").

Expected: la respuesta tiene un tono cálido y cercano, no el tono neutro/robótico de antes. Al preguntar por un trámite de Defensa del Consumidor o Secretaría de Trabajo (no solo Registro Civil), el comportamiento es igual de bueno — confirma que sacar la mención hardcodeada de organismo no rompió nada.

- [ ] **Step 2: Confirmar los datos nuevos en el panel derecho**

Preguntar por un trámite que identifique alguno concreto (ej. "¿qué necesito para un acta de nacimiento?" y elegir uno de los dos que ofrezca).

Expected: el panel derecho muestra, además de lo que ya mostraba, costo, modalidad, duración, pasos y enlaces oficiales (las secciones que tengan datos).

- [ ] **Step 3: Confirmar vía API directa que el endpoint devuelve los campos nuevos**

Run: `curl -s http://localhost:8000/tramites/<un-id-real-de-la-data-cargada> | python3 -m json.tool`
Expected: la respuesta incluye `costo`, `modalidad`, `duracion`, `pasos`, `enlaces_oficiales` con valores reales (no vacíos, dado que son datos reales ya cargados).

- [ ] **Step 4: Correr toda la suite de tests una última vez**

Run: `cd backend && source .venv/bin/activate && pytest -v`
Run: `cd frontend && npx tsc --noEmit`
Expected: PASS en ambos.
