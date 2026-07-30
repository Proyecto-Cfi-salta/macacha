# Panel derecho: top 3 al inicio y candidatos ambiguos — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** El panel derecho del chat muestra el top 3 global de trámites más consultados cuando no hay ninguno identificado todavía, muestra nombre + descripción de los candidatos cuando hay ambigüedad ("denuncia" → laboral o consumidor), y sigue mostrando el detalle completo cuando la charla se resuelve a un único trámite.

**Architecture:** Backend expone dos cosas nuevas: un endpoint de ranking global (`GET /tramites-frecuentes`) y un campo `candidatos_ambiguos` en el evento SSE `"fin"` del chat (calculado en `orchestrator.py` a partir de los candidatos que ya se buscaban internamente pero se descartaban). Frontend reemplaza el hook `useTramiteActual` por `usePanelTramite`, que devuelve un estado con 4 formas (`cargando` / `top3` / `ambiguo` / `tramite`) según lo que haya en los mensajes, y `app/page.tsx` elige qué componente renderizar en el panel derecho según ese estado.

**Tech Stack:** Python 3.12 / FastAPI / psycopg (backend), Next.js 15 / React 19 / TypeScript / Vitest (frontend).

## Global Constraints

- `candidatos_ambiguos` y `fuentes` nunca vienen los dos no-vacíos en el mismo evento `"fin"` — uno de los dos siempre es `[]`.
- El top 3 es **global** (no filtrado por organismo) — no reemplaza el endpoint existente `GET /organismos/{organismo}/tramites-frecuentes`, que queda como está.
- Los candidatos ambiguos se acotan a **3 como máximo**, en el orden ya rankeado que devuelve `buscar_tramite`.
- El contador `veces_consultado` **no** se incrementa para candidatos ambiguos, solo para `fuentes` confirmadas (esto ya es así hoy, no cambia).
- El texto que se envía al chat al clickear un trámite (ambiguo o del top 3) es siempre `` `Quiero información sobre ${nombre_oficial}.` ``.
- `hooks/useTramitesFrecuentes.ts` (el acotado por organismo) no se toca — sigue sin uso.

---

## Task 1: Backend — ranking global de trámites más consultados (repository)

**Files:**
- Modify: `backend/ingest/repository.py:123-139` (después de `obtener_tramites_frecuentes`)
- Test: `backend/tests/test_repository.py`

**Interfaces:**
- Produces: `obtener_top_tramites(conn, limite: int = 3) -> list[dict]`, cada dict con `{"tramite_id": str, "nombre_oficial": str, "veces_consultado": int}`.

- [ ] **Step 1: Escribir los tests que van a fallar**

Agregar al final de `backend/tests/test_repository.py`:

```python
def test_obtener_top_tramites_ordena_global_mezclando_organismos(db_conn, clean_db):
    rc_id = repo.upsert_organismo(db_conn, "Registro Civil")
    otro_id = repo.upsert_organismo(db_conn, "Rentas")
    repo.upsert_tramite(db_conn, "RC-0001", rc_id, "Actas", "Actas Regulares")
    repo.upsert_tramite(db_conn, "RE-0001", otro_id, "Impuestos", "Pago de Rentas")
    db_conn.commit()

    repo.incrementar_veces_consultado(db_conn, "RC-0001")
    repo.incrementar_veces_consultado(db_conn, "RE-0001")
    repo.incrementar_veces_consultado(db_conn, "RE-0001")
    db_conn.commit()

    resultado = repo.obtener_top_tramites(db_conn)

    assert resultado == [
        {"tramite_id": "RE-0001", "nombre_oficial": "Pago de Rentas", "veces_consultado": 2},
        {"tramite_id": "RC-0001", "nombre_oficial": "Actas Regulares", "veces_consultado": 1},
    ]


def test_obtener_top_tramites_excluye_no_consultados(db_conn, clean_db):
    organismo_id = repo.upsert_organismo(db_conn, "Registro Civil")
    repo.upsert_tramite(db_conn, "RC-0001", organismo_id, "Actas", "Actas Regulares")
    db_conn.commit()

    assert repo.obtener_top_tramites(db_conn) == []


def test_obtener_top_tramites_respeta_el_limite(db_conn, clean_db):
    organismo_id = repo.upsert_organismo(db_conn, "Registro Civil")
    for i in range(1, 6):
        tramite_id = f"RC-000{i}"
        repo.upsert_tramite(db_conn, tramite_id, organismo_id, "Actas", f"Trámite {i}")
        db_conn.commit()
        repo.incrementar_veces_consultado(db_conn, tramite_id)
        db_conn.commit()

    resultado = repo.obtener_top_tramites(db_conn)

    assert len(resultado) == 3
```

- [ ] **Step 2: Correr los tests para confirmar que fallan**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_repository.py -k obtener_top_tramites -v`
Expected: FAIL con `AttributeError: module 'ingest.repository' has no attribute 'obtener_top_tramites'`.

- [ ] **Step 3: Implementar `obtener_top_tramites`**

En `backend/ingest/repository.py`, después de la función `obtener_tramites_frecuentes` (línea 139):

```python
def obtener_top_tramites(conn, limite: int = 3) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT t.id, t.nombre_oficial, t.veces_consultado
            FROM tramites t
            WHERE t.veces_consultado > 0
            ORDER BY t.veces_consultado DESC, t.id ASC
            LIMIT %s
            """,
            (limite,),
        )
        return [
            {"tramite_id": row[0], "nombre_oficial": row[1], "veces_consultado": row[2]}
            for row in cur.fetchall()
        ]
```

- [ ] **Step 4: Correr los tests para confirmar que pasan**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_repository.py -v`
Expected: PASS (todos, incluidos los 3 nuevos).

- [ ] **Step 5: Commit**

```bash
cd /home/seba/Escritorio/workspace/macacha
git add backend/ingest/repository.py backend/tests/test_repository.py
git commit -m "feat: agregar obtener_top_tramites (ranking global sin filtro de organismo)"
```

---

## Task 2: Backend — endpoint `GET /tramites-frecuentes`

**Files:**
- Modify: `backend/agent/api.py:22-27` (import) y después de `agent/api.py:129-132` (endpoint existente)
- Test: `backend/tests/test_api.py`

**Interfaces:**
- Consumes: `obtener_top_tramites(conn, limite=3)` de Task 1.
- Produces: endpoint `GET /tramites-frecuentes` → `list[dict]` (mismo shape que Task 1).

- [ ] **Step 1: Escribir los tests que van a fallar**

Agregar al final de `backend/tests/test_api.py` (ya importa `urllib.parse`, `repo`, `TestClient`, `obtener_pool`):

```python
def test_get_tramites_frecuentes_global_devuelve_top_3(db_conn, clean_db):
    rc_id = repo.upsert_organismo(db_conn, "Registro Civil")
    otro_id = repo.upsert_organismo(db_conn, "Rentas")
    repo.upsert_tramite(db_conn, "RC-0001", rc_id, "Actas", "Actas Regulares")
    repo.upsert_tramite(db_conn, "RE-0001", otro_id, "Impuestos", "Pago de Rentas")
    db_conn.commit()
    repo.incrementar_veces_consultado(db_conn, "RE-0001")
    repo.incrementar_veces_consultado(db_conn, "RE-0001")
    repo.incrementar_veces_consultado(db_conn, "RC-0001")
    db_conn.commit()

    api.app.dependency_overrides[obtener_pool] = lambda: _FakePool(db_conn)
    client = TestClient(api.app)
    try:
        respuesta = client.get("/tramites-frecuentes")
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.status_code == 200
    assert respuesta.json() == [
        {"tramite_id": "RE-0001", "nombre_oficial": "Pago de Rentas", "veces_consultado": 2},
        {"tramite_id": "RC-0001", "nombre_oficial": "Actas Regulares", "veces_consultado": 1},
    ]


def test_get_tramites_frecuentes_global_sin_consultas_devuelve_lista_vacia(db_conn, clean_db):
    api.app.dependency_overrides[obtener_pool] = lambda: _FakePool(db_conn)
    client = TestClient(api.app)
    try:
        respuesta = client.get("/tramites-frecuentes")
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.status_code == 200
    assert respuesta.json() == []
```

- [ ] **Step 2: Correr los tests para confirmar que fallan**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_api.py -k tramites_frecuentes_global -v`
Expected: FAIL con 404 (la ruta no existe todavía).

- [ ] **Step 3: Implementar el endpoint**

En `backend/agent/api.py`, agregar `obtener_top_tramites` al import existente (línea 22-27):

```python
from ingest.repository import (
    incrementar_veces_consultado,
    obtener_snapshot_vigente,
    obtener_top_tramites,
    obtener_tramites_frecuentes,
)
```

Y agregar el endpoint nuevo justo después de `tramites_frecuentes` (después de la línea 132):

```python
@app.get("/tramites-frecuentes")
def top_tramites(pool=Depends(obtener_pool)):
    with pool.connection() as conn:
        return obtener_top_tramites(conn)
```

- [ ] **Step 4: Correr los tests para confirmar que pasan**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_api.py -v`
Expected: PASS (todos).

- [ ] **Step 5: Commit**

```bash
cd /home/seba/Escritorio/workspace/macacha
git add backend/agent/api.py backend/tests/test_api.py
git commit -m "feat: agregar endpoint GET /tramites-frecuentes con el ranking global"
```

---

## Task 3: Backend — candidatos ambiguos en el evento `"fin"` del chat

**Files:**
- Modify: `backend/agent/orchestrator.py:69-174`
- Test: `backend/tests/test_orchestrator.py`

**Interfaces:**
- Produces: evento `"fin"` con forma `{"tipo": "fin", "fuentes": [...], "candidatos_ambiguos": [...]}`; cada candidato ambiguo es `{"tramite_id": str, "nombre_oficial": str, "descripcion": str}`.

- [ ] **Step 1: Actualizar las aserciones existentes que van a romperse**

El evento `"fin"` va a tener una clave nueva, así que las comparaciones exactas de diccionario que no la incluyen van a fallar. Actualizar estas 4 (son las únicas que hacen `eventos[-1] == {...}` completo, no `eventos[-1]["fuentes"]`):

En `backend/tests/test_orchestrator.py:70`:
```python
    assert eventos[-1] == {"tipo": "fin", "fuentes": [], "candidatos_ambiguos": []}
```

En `backend/tests/test_orchestrator.py:117-126`:
```python
    assert eventos[-1] == {
        "tipo": "fin",
        "fuentes": [
            {
                "tramite_id": "RC-0001",
                "nombre_oficial": "Actas Regulares",
                "fuente_url": "https://registrocivilsalta.gob.ar/",
            }
        ],
        "candidatos_ambiguos": [],
    }
```

En `backend/tests/test_orchestrator.py:348` (dentro de `test_procesar_turno_busqueda_ambigua_sin_nombre_en_el_texto_no_cita_fuentes`) — reemplazar esa función completa por una versión que además verifica los candidatos ambiguos:

```python
def test_procesar_turno_busqueda_ambigua_sin_nombre_en_el_texto_no_cita_fuentes(db_conn, clean_db):
    _armar_tramite_de_prueba(db_conn, tramite_id="RC-0002", nombre_oficial="Acta de Matrimonio")
    _armar_tramite_de_prueba(db_conn, tramite_id="RC-0001", nombre_oficial="Acta de Nacimiento")
    session_id = str(uuid.uuid4())

    candidatos = buscar_tramite(db_conn, _fake_embed_fn, _fake_rerank_fn, "acta")
    assert len(candidatos) == 2

    chat_client = _FakeChatClient(
        [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "buscar_tramite", "arguments": '{"query": "acta"}'},
                    }
                ],
            },
            {"role": "assistant", "content": "¿Cuál de las dos actas te interesa?", "tool_calls": None},
        ]
    )

    eventos = list(
        procesar_turno(
            db_conn, chat_client, _fake_embed_fn, _fake_rerank_fn, session_id, "qué necesito para un acta"
        )
    )
    db_conn.commit()

    assert eventos[-1]["fuentes"] == []
    candidatos_ambiguos = eventos[-1]["candidatos_ambiguos"]
    assert {c["tramite_id"]: c["descripcion"] for c in candidatos_ambiguos} == {
        "RC-0001": "Descripción",
        "RC-0002": "Descripción",
    }
```

En `backend/tests/test_orchestrator.py:382`:
```python
    assert eventos[-1] == {"tipo": "fin", "fuentes": [], "candidatos_ambiguos": []}
```

- [ ] **Step 2: Escribir el test nuevo que va a fallar**

Agregar después de `test_procesar_turno_busqueda_con_varios_candidatos_cita_el_mencionado_en_el_texto` (la que hoy termina en la línea 264):

```python
def test_procesar_turno_resuelto_no_expone_candidatos_ambiguos(db_conn, clean_db):
    _armar_tramite_de_prueba(db_conn, tramite_id="RC-0002", nombre_oficial="Acta de Matrimonio")
    _armar_tramite_de_prueba(db_conn, tramite_id="RC-0001", nombre_oficial="Acta de Nacimiento")
    session_id = str(uuid.uuid4())

    chat_client = _FakeChatClient(
        [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "buscar_tramite", "arguments": '{"query": "acta"}'},
                    }
                ],
            },
            {
                "role": "assistant",
                "content": "El trámite que necesitás es Acta de Nacimiento.",
                "tool_calls": None,
            },
        ]
    )

    eventos = list(
        procesar_turno(
            db_conn, chat_client, _fake_embed_fn, _fake_rerank_fn, session_id, "qué necesito para un acta"
        )
    )
    db_conn.commit()

    assert eventos[-1]["candidatos_ambiguos"] == []
```

- [ ] **Step 3: Correr los tests para confirmar que fallan**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_orchestrator.py -v`
Expected: FAIL — `KeyError: 'candidatos_ambiguos'` en varios tests.

- [ ] **Step 4: Implementar `_armar_candidatos_ambiguos` y usarla en los dos `yield` de `"fin"`**

En `backend/agent/orchestrator.py`, agregar esta función después de `_armar_fuentes` (al final del archivo):

```python
def _armar_candidatos_ambiguos(conn, candidatos_buscados: dict[str, str]) -> list[dict]:
    candidatos_ambiguos = []
    for tramite_id in list(candidatos_buscados.keys())[:3]:
        snapshot = obtener_snapshot_vigente(conn, tramite_id)
        if snapshot is None:
            continue
        candidatos_ambiguos.append(
            {
                "tramite_id": tramite_id,
                "nombre_oficial": snapshot["nombre_oficial"],
                "descripcion": snapshot.get("descripcion", ""),
            }
        )
    return candidatos_ambiguos
```

Modificar el primer `yield` de `"fin"` (línea 94, dentro del `if not tool_calls:`):

```python
        if not tool_calls:
            _citar_candidatos_mencionados(contenido, candidatos_buscados, tramites_citados)
            sessions.guardar_mensaje(
                conn,
                session_id,
                rol="assistant",
                contenido=contenido,
                proveedor=proveedor,
            )
            yield {
                "tipo": "fin",
                "fuentes": _armar_fuentes(conn, tramites_citados),
                "candidatos_ambiguos": (
                    [] if tramites_citados else _armar_candidatos_ambiguos(conn, candidatos_buscados)
                ),
            }
            return
```

Y el segundo `yield` de `"fin"` (líneas 137-140, el camino de "iteraciones agotadas"):

```python
    mensaje_agotado = "No pude resolver tu consulta en este momento. ¿Podés reformularla?"
    sessions.guardar_mensaje(conn, session_id, rol="assistant", contenido=mensaje_agotado)
    yield {"tipo": "texto", "delta": mensaje_agotado}
    yield {
        "tipo": "fin",
        "fuentes": _armar_fuentes(conn, tramites_citados),
        "candidatos_ambiguos": (
            [] if tramites_citados else _armar_candidatos_ambiguos(conn, candidatos_buscados)
        ),
    }
```

- [ ] **Step 5: Correr los tests para confirmar que pasan**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_orchestrator.py -v`
Expected: PASS (todos, incluidos los 2 nuevos y los 4 actualizados).

- [ ] **Step 6: Correr toda la suite del backend**

Run: `cd backend && source .venv/bin/activate && python -m pytest -v`
Expected: PASS (154 + los nuevos de Tasks 1-3).

- [ ] **Step 7: Commit**

```bash
cd /home/seba/Escritorio/workspace/macacha
git add backend/agent/orchestrator.py backend/tests/test_orchestrator.py
git commit -m "feat: exponer candidatos ambiguos en el evento fin de procesar_turno"
```

---

## Task 4: Frontend — tipos y fetch para top 3 y candidatos ambiguos

**Files:**
- Modify: `frontend/lib/api.ts`
- Modify: `frontend/hooks/useChatStream.ts`
- Modify: `frontend/hooks/useChatStream.test.ts`

**Interfaces:**
- Produces: `obtenerTopTramites(): Promise<TramiteFrecuente[]>`; tipo `CandidatoAmbiguo`; `Mensaje.candidatosAmbiguos?: CandidatoAmbiguo[]`; `EventoSSE` (caso `"fin"`) con `candidatos_ambiguos: CandidatoAmbiguo[]`.

- [ ] **Step 1: Escribir los tests que van a fallar**

Reemplazar en `frontend/hooks/useChatStream.test.ts` el test `"parsea un evento de fin con fuentes"` (líneas 15-31) por estos dos:

```ts
  it("parsea un evento de fin con fuentes y candidatos ambiguos vacíos", () => {
    const bloque =
      'data: {"tipo":"fin","fuentes":[{"tramite_id":"RC-0001","nombre_oficial":"Actas Regulares","fuente_url":"https://x"}],"candidatos_ambiguos":[]}';

    expect(parsearLineasSSE(bloque)).toEqual([
      {
        tipo: "fin",
        fuentes: [
          {
            tramite_id: "RC-0001",
            nombre_oficial: "Actas Regulares",
            fuente_url: "https://x",
          },
        ],
        candidatos_ambiguos: [],
      },
    ]);
  });

  it("parsea un evento de fin con candidatos ambiguos", () => {
    const bloque =
      'data: {"tipo":"fin","fuentes":[],"candidatos_ambiguos":[{"tramite_id":"TR-0002","nombre_oficial":"Denuncia laboral","descripcion":"Reclamos laborales."}]}';

    expect(parsearLineasSSE(bloque)).toEqual([
      {
        tipo: "fin",
        fuentes: [],
        candidatos_ambiguos: [
          {
            tramite_id: "TR-0002",
            nombre_oficial: "Denuncia laboral",
            descripcion: "Reclamos laborales.",
          },
        ],
      },
    ]);
  });
```

- [ ] **Step 2: Correr los tests para confirmar que fallan**

Run: `cd frontend && npm test -- --run`
Expected: FAIL — TypeScript error porque `EventoSSE` todavía no tiene `candidatos_ambiguos`, y el `toEqual` no matchea porque `parsearLineasSSE` no lo agrega.

- [ ] **Step 3: Implementar los tipos y el fetch**

En `frontend/lib/api.ts`, agregar después de `obtenerTramitesFrecuentes`:

```ts
export async function obtenerTopTramites(): Promise<TramiteFrecuente[]> {
  const respuesta = await fetch(`${BASE_URL}/tramites-frecuentes`);
  if (!respuesta.ok) {
    return [];
  }
  return respuesta.json();
}
```

En `frontend/hooks/useChatStream.ts`, reemplazar las líneas 6-22 (tipos `Fuente`, `Mensaje`, `EventoSSE`) por:

```ts
export type Fuente = {
  tramite_id: string;
  nombre_oficial: string;
  fuente_url: string | null;
};

export type CandidatoAmbiguo = {
  tramite_id: string;
  nombre_oficial: string;
  descripcion: string;
};

export type Mensaje = {
  rol: "user" | "assistant";
  contenido: string;
  fuentes?: Fuente[];
  candidatosAmbiguos?: CandidatoAmbiguo[];
  error?: boolean;
};

export type EventoSSE =
  | { tipo: "texto"; delta: string }
  | { tipo: "fin"; fuentes: Fuente[]; candidatos_ambiguos: CandidatoAmbiguo[] }
  | { tipo: "error"; mensaje: string };
```

Y en la función `aplicarEvento` (dentro de `useChatStream`), reemplazar la rama `"fin"`:

```ts
      } else if (evento.tipo === "fin") {
        copia[copia.length - 1] = {
          ...ultimo,
          fuentes: evento.fuentes,
          candidatosAmbiguos: evento.candidatos_ambiguos,
        };
```

- [ ] **Step 4: Correr los tests y el type-check para confirmar que pasan**

Run: `cd frontend && npx tsc --noEmit && npm test -- --run`
Expected: PASS (sin errores de tipo, 19 tests de Vitest incluyendo los 2 nuevos).

- [ ] **Step 5: Commit**

```bash
cd /home/seba/Escritorio/workspace/macacha
git add frontend/lib/api.ts frontend/hooks/useChatStream.ts frontend/hooks/useChatStream.test.ts
git commit -m "feat: agregar tipos y fetch de top 3 global y candidatos ambiguos"
```

---

## Task 5: Frontend — hook `usePanelTramite` (reemplaza `useTramiteActual`)

**Files:**
- Create: `frontend/hooks/usePanelTramite.ts`
- Create: `frontend/hooks/usePanelTramite.test.ts`
- Delete: `frontend/hooks/useTramiteActual.ts`
- Delete: `frontend/hooks/useTramiteActual.test.ts`

**Interfaces:**
- Consumes: `obtenerTramite`, `obtenerTopTramites` de `lib/api.ts`; `Mensaje`, `CandidatoAmbiguo` de `hooks/useChatStream.ts` (Task 4).
- Produces: `determinarEstadoRelevante(mensajes: Mensaje[]): EstadoRelevante` (función pura, exportada para tests); `usePanelTramite(mensajes: Mensaje[]): VistaPanel`, donde:

```ts
export type VistaPanel =
  | { tipo: "cargando" }
  | { tipo: "top3"; tramites: TramiteFrecuente[] }
  | { tipo: "ambiguo"; candidatos: CandidatoAmbiguo[] }
  | { tipo: "tramite"; tramite: TramiteDetalle };
```

- [ ] **Step 1: Escribir el test que va a fallar**

Crear `frontend/hooks/usePanelTramite.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { determinarEstadoRelevante } from "./usePanelTramite";
import type { Mensaje } from "./useChatStream";

describe("determinarEstadoRelevante", () => {
  it("devuelve idle si ningún mensaje tiene fuentes ni candidatos ambiguos", () => {
    const mensajes: Mensaje[] = [
      { rol: "user", contenido: "hola" },
      { rol: "assistant", contenido: "hola, en qué te ayudo?" },
    ];
    expect(determinarEstadoRelevante(mensajes)).toEqual({ tipo: "idle" });
  });

  it("devuelve el tramite_id de la última fuente del último mensaje con fuentes", () => {
    const mensajes: Mensaje[] = [
      {
        rol: "assistant",
        contenido: "...",
        fuentes: [{ tramite_id: "RC-0001", nombre_oficial: "Actas Regulares", fuente_url: null }],
      },
      { rol: "user", contenido: "y para otro trámite?" },
      {
        rol: "assistant",
        contenido: "...",
        fuentes: [{ tramite_id: "RC-0002", nombre_oficial: "Otro trámite", fuente_url: null }],
      },
    ];
    expect(determinarEstadoRelevante(mensajes)).toEqual({ tipo: "tramite", tramiteId: "RC-0002" });
  });

  it("dentro de un mismo mensaje, toma el último tramite_id de la lista de fuentes", () => {
    const mensajes: Mensaje[] = [
      {
        rol: "assistant",
        contenido: "...",
        fuentes: [
          { tramite_id: "RC-0001", nombre_oficial: "Actas Regulares", fuente_url: null },
          { tramite_id: "RC-0003", nombre_oficial: "Otro trámite más", fuente_url: null },
        ],
      },
    ];
    expect(determinarEstadoRelevante(mensajes)).toEqual({ tipo: "tramite", tramiteId: "RC-0003" });
  });

  it("ignora mensajes con fuentes vacías y usa el último no vacío", () => {
    const mensajes: Mensaje[] = [
      {
        rol: "assistant",
        contenido: "...",
        fuentes: [{ tramite_id: "RC-0001", nombre_oficial: "Actas Regulares", fuente_url: null }],
      },
      { rol: "assistant", contenido: "no encontré nada", fuentes: [] },
    ];
    expect(determinarEstadoRelevante(mensajes)).toEqual({ tipo: "tramite", tramiteId: "RC-0001" });
  });

  it("devuelve los candidatos ambiguos del último mensaje que los tiene", () => {
    const candidatos = [
      {
        tramite_id: "TR-0002",
        nombre_oficial: "Denuncia laboral",
        descripcion: "Reclamos laborales.",
      },
      {
        tramite_id: "DC-0001",
        nombre_oficial: "Denuncia ante Defensa del Consumidor",
        descripcion: "Reclamos de consumo.",
      },
    ];
    const mensajes: Mensaje[] = [
      { rol: "user", contenido: "hola como hago una denuncia?" },
      { rol: "assistant", contenido: "...", candidatosAmbiguos: candidatos },
    ];
    expect(determinarEstadoRelevante(mensajes)).toEqual({ tipo: "ambiguo", candidatos });
  });

  it("una vez resuelto a un trámite puntual, ignora la ambigüedad de un mensaje anterior", () => {
    const mensajes: Mensaje[] = [
      {
        rol: "assistant",
        contenido: "...",
        candidatosAmbiguos: [
          {
            tramite_id: "TR-0002",
            nombre_oficial: "Denuncia laboral",
            descripcion: "Reclamos laborales.",
          },
        ],
      },
      { rol: "user", contenido: "la laboral" },
      {
        rol: "assistant",
        contenido: "...",
        fuentes: [{ tramite_id: "TR-0002", nombre_oficial: "Denuncia laboral", fuente_url: null }],
      },
    ];
    expect(determinarEstadoRelevante(mensajes)).toEqual({ tipo: "tramite", tramiteId: "TR-0002" });
  });
});
```

- [ ] **Step 2: Correr el test para confirmar que falla**

Run: `cd frontend && npm test -- --run usePanelTramite`
Expected: FAIL — no existe el módulo `./usePanelTramite`.

- [ ] **Step 3: Implementar `usePanelTramite.ts`**

Crear `frontend/hooks/usePanelTramite.ts`:

```ts
"use client";

import { useEffect, useState } from "react";
import { obtenerTramite, obtenerTopTramites, TramiteDetalle, TramiteFrecuente } from "../lib/api";
import type { CandidatoAmbiguo, Mensaje } from "./useChatStream";

export type EstadoRelevante =
  | { tipo: "tramite"; tramiteId: string }
  | { tipo: "ambiguo"; candidatos: CandidatoAmbiguo[] }
  | { tipo: "idle" };

export function determinarEstadoRelevante(mensajes: Mensaje[]): EstadoRelevante {
  for (let i = mensajes.length - 1; i >= 0; i--) {
    const fuentes = mensajes[i].fuentes;
    if (fuentes && fuentes.length > 0) {
      return { tipo: "tramite", tramiteId: fuentes[fuentes.length - 1].tramite_id };
    }
    const candidatos = mensajes[i].candidatosAmbiguos;
    if (candidatos && candidatos.length > 0) {
      return { tipo: "ambiguo", candidatos };
    }
  }
  return { tipo: "idle" };
}

export type VistaPanel =
  | { tipo: "cargando" }
  | { tipo: "top3"; tramites: TramiteFrecuente[] }
  | { tipo: "ambiguo"; candidatos: CandidatoAmbiguo[] }
  | { tipo: "tramite"; tramite: TramiteDetalle };

export function usePanelTramite(mensajes: Mensaje[]): VistaPanel {
  const estado = determinarEstadoRelevante(mensajes);
  const tramiteId = estado.tipo === "tramite" ? estado.tramiteId : null;
  const [tramite, setTramite] = useState<TramiteDetalle | null>(null);
  const [tramites, setTramites] = useState<TramiteFrecuente[] | null>(null);

  useEffect(() => {
    let cancelado = false;
    if (!tramiteId) {
      setTramite(null);
      return;
    }
    obtenerTramite(tramiteId)
      .then((resultado) => {
        if (!cancelado) setTramite(resultado);
      })
      .catch(() => {
        if (!cancelado) setTramite(null);
      });
    return () => {
      cancelado = true;
    };
  }, [tramiteId]);

  useEffect(() => {
    let cancelado = false;
    if (estado.tipo !== "idle") {
      return;
    }
    obtenerTopTramites()
      .then((resultado) => {
        if (!cancelado) setTramites(resultado);
      })
      .catch(() => {
        if (!cancelado) setTramites([]);
      });
    return () => {
      cancelado = true;
    };
  }, [estado.tipo]);

  if (estado.tipo === "tramite") {
    return tramite ? { tipo: "tramite", tramite } : { tipo: "cargando" };
  }
  if (estado.tipo === "ambiguo") {
    return { tipo: "ambiguo", candidatos: estado.candidatos };
  }
  return tramites ? { tipo: "top3", tramites } : { tipo: "cargando" };
}
```

- [ ] **Step 4: Borrar los archivos reemplazados**

```bash
cd /home/seba/Escritorio/workspace/macacha
rm frontend/hooks/useTramiteActual.ts frontend/hooks/useTramiteActual.test.ts
```

- [ ] **Step 5: Correr el test y el type-check para confirmar que pasan**

Run: `cd frontend && npx tsc --noEmit && npm test -- --run`
Expected: FAIL en el type-check (esperado en este paso: `app/page.tsx` todavía importa `useTramiteActual`, que ya no existe) — esto se resuelve en Task 8. Confirmar que el error reportado es únicamente sobre `app/page.tsx` importando `useTramiteActual`, y que `npm test -- --run usePanelTramite` (sin `tsc`) pasa:

Run: `cd frontend && npm test -- --run usePanelTramite`
Expected: PASS (7 tests).

- [ ] **Step 6: Commit**

```bash
cd /home/seba/Escritorio/workspace/macacha
git add frontend/hooks/usePanelTramite.ts frontend/hooks/usePanelTramite.test.ts
git rm frontend/hooks/useTramiteActual.ts frontend/hooks/useTramiteActual.test.ts
git commit -m "feat: reemplazar useTramiteActual por usePanelTramite (top3/ambiguo/tramite)"
```

(El type-check de `app/page.tsx` va a quedar roto hasta Task 8 — es esperado, se corrige ahí.)

---

## Task 6: Frontend — componente `TramitesAmbiguosPanel`

**Files:**
- Create: `frontend/components/TramitesAmbiguosPanel.tsx`

**Interfaces:**
- Consumes: `CandidatoAmbiguo` de `hooks/useChatStream.ts` (Task 4).
- Produces: `TramitesAmbiguosPanel({ candidatos, onPreguntar, preguntarDeshabilitado })`.

- [ ] **Step 1: Implementar el componente**

Crear `frontend/components/TramitesAmbiguosPanel.tsx`:

```tsx
"use client";

import type { CandidatoAmbiguo } from "../hooks/useChatStream";

export function TramitesAmbiguosPanel({
  candidatos,
  onPreguntar,
  preguntarDeshabilitado,
}: {
  candidatos: CandidatoAmbiguo[];
  onPreguntar: (mensaje: string) => void;
  preguntarDeshabilitado: boolean;
}) {
  return (
    <div>
      <h2 className="font-semibold">¿Cuál de estos trámites te interesa?</h2>
      <ul className="mt-2 space-y-3">
        {candidatos.map((candidato) => (
          <li key={candidato.tramite_id}>
            <button
              type="button"
              onClick={() => onPreguntar(`Quiero información sobre ${candidato.nombre_oficial}.`)}
              disabled={preguntarDeshabilitado}
              className="w-full rounded border border-gray-200 p-2 text-left text-sm hover:bg-gray-50 disabled:opacity-50"
            >
              <span className="font-medium">{candidato.nombre_oficial}</span>
              <p className="mt-1 text-gray-500">{candidato.descripcion}</p>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
```

- [ ] **Step 2: Correr el type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: sin errores nuevos atribuibles a este archivo (el error de `useTramiteActual` en `page.tsx` sigue ahí, se resuelve en Task 8).

- [ ] **Step 3: Commit**

```bash
cd /home/seba/Escritorio/workspace/macacha
git add frontend/components/TramitesAmbiguosPanel.tsx
git commit -m "feat: agregar TramitesAmbiguosPanel para mostrar candidatos ambiguos"
```

---

## Task 7: Frontend — `TramitesFrecuentesPanel` clickeable

**Files:**
- Modify: `frontend/components/TramitesFrecuentesPanel.tsx`

**Interfaces:**
- Produces: `TramitesFrecuentesPanel({ tramites, onPreguntar, preguntarDeshabilitado })` (antes solo recibía `tramites`).

- [ ] **Step 1: Modificar el componente**

Reemplazar el contenido completo de `frontend/components/TramitesFrecuentesPanel.tsx`:

```tsx
import type { TramiteFrecuente } from "../lib/api";

export function TramitesFrecuentesPanel({
  tramites,
  onPreguntar,
  preguntarDeshabilitado,
}: {
  tramites: TramiteFrecuente[];
  onPreguntar: (mensaje: string) => void;
  preguntarDeshabilitado: boolean;
}) {
  if (tramites.length === 0) {
    return (
      <p className="text-sm text-gray-400">
        Los trámites más consultados van a aparecer acá.
      </p>
    );
  }

  return (
    <div>
      <h2 className="font-semibold">Más consultados</h2>
      <ol className="mt-2 space-y-2 text-sm">
        {tramites.map((tramite, indice) => (
          <li key={tramite.tramite_id}>
            <button
              type="button"
              onClick={() => onPreguntar(`Quiero información sobre ${tramite.nombre_oficial}.`)}
              disabled={preguntarDeshabilitado}
              className="flex w-full justify-between gap-2 rounded p-1 text-left hover:bg-gray-50 disabled:opacity-50"
            >
              <span>
                {indice + 1}. {tramite.nombre_oficial}
              </span>
              <span className="text-gray-400">{tramite.veces_consultado}</span>
            </button>
          </li>
        ))}
      </ol>
    </div>
  );
}
```

- [ ] **Step 2: Correr el type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: mismo estado que Task 6 (el único error pendiente es el de `page.tsx`, que todavía no pasa `onPreguntar`/`preguntarDeshabilitado` porque no invoca este componente — se resuelve en Task 8).

- [ ] **Step 3: Commit**

```bash
cd /home/seba/Escritorio/workspace/macacha
git add frontend/components/TramitesFrecuentesPanel.tsx
git commit -m "feat: hacer clickeables los items de TramitesFrecuentesPanel"
```

---

## Task 8: Frontend — wiring en `app/page.tsx`

**Files:**
- Modify: `frontend/app/page.tsx`
- Modify: `frontend/components/TramiteInfoPanel.tsx:7-24`

**Interfaces:**
- Consumes: `usePanelTramite` (Task 5), `TramitesAmbiguosPanel` (Task 6), `TramitesFrecuentesPanel` (Task 7).

- [ ] **Step 1: Simplificar `TramiteInfoPanel` (ya no recibe `null`)**

Con este cambio, `TramiteInfoPanel` solo se va a renderizar cuando ya hay un trámite resuelto, así que el prop deja de aceptar `null` y se borra la rama de placeholder. En `frontend/components/TramiteInfoPanel.tsx`, reemplazar las líneas 7-24:

```tsx
export function TramiteInfoPanel({
  tramite,
  onPreguntar,
  preguntarDeshabilitado,
}: {
  tramite: TramiteDetalle;
  onPreguntar: (mensaje: string) => void;
  preguntarDeshabilitado: boolean;
}) {
  const { estaTildado, toggle } = useChecklist(tramite.tramite_id);
```

(Se elimina el bloque `if (!tramite) { return <p>...</p>; }` que estaba justo después.)

- [ ] **Step 2: Reescribir `app/page.tsx`**

Reemplazar el contenido completo de `frontend/app/page.tsx`:

```tsx
"use client";

import { useState } from "react";
import { ChatInput } from "../components/ChatInput";
import { ChatMessage } from "../components/ChatMessage";
import { TramiteInfoPanel } from "../components/TramiteInfoPanel";
import { TramitesAmbiguosPanel } from "../components/TramitesAmbiguosPanel";
import { TramitesFrecuentesPanel } from "../components/TramitesFrecuentesPanel";
import { useChatStream } from "../hooks/useChatStream";
import { usePanelTramite } from "../hooks/usePanelTramite";
import { useSession } from "../hooks/useSession";

export default function Home() {
  const { sessionId } = useSession();

  if (!sessionId) {
    return null;
  }

  return <Chat sessionId={sessionId} />;
}

type Tab = "chat" | "info";

function Chat({ sessionId }: { sessionId: string }) {
  const { mensajes, enviando, enviarMensaje } = useChatStream(sessionId);
  const vista = usePanelTramite(mensajes);
  const [tab, setTab] = useState<Tab>("chat");

  function preguntarSobre(mensaje: string) {
    enviarMensaje(mensaje);
    setTab("chat");
  }

  return (
    <div className="mx-auto flex h-screen max-w-6xl flex-col md:flex-row">
      <nav className="flex border-b border-gray-200 md:hidden">
        <TabButton activo={tab === "chat"} onClick={() => setTab("chat")}>
          Chat
        </TabButton>
        <TabButton activo={tab === "info"} onClick={() => setTab("info")}>
          Info del trámite
        </TabButton>
      </nav>

      <main
        className={`min-w-0 flex-1 flex-col ${tab === "chat" ? "flex" : "hidden"} md:flex`}
      >
        <header className="border-b border-gray-200 p-4">
          <h1 className="text-lg font-semibold">Macacha</h1>
          <p className="text-sm text-gray-500">
            Asistente de trámites — Provincia de Salta
          </p>
        </header>
        <div className="flex-1 space-y-3 overflow-y-auto p-4">
          {mensajes.map((mensaje, indice) => (
            <ChatMessage
              key={indice}
              mensaje={mensaje}
              onReintentar={
                mensaje.error && !enviando
                  ? () => {
                      const anterior = mensajes[indice - 1];
                      if (anterior) enviarMensaje(anterior.contenido);
                    }
                  : undefined
              }
            />
          ))}
          {enviando && <p className="text-sm text-gray-400">escribiendo…</p>}
        </div>
        <ChatInput disabled={enviando} onEnviar={enviarMensaje} />
      </main>

      <aside
        className={`w-full flex-1 overflow-y-auto border-gray-200 p-4 md:block md:flex-none md:w-72 md:border-l ${
          tab === "info" ? "block" : "hidden"
        }`}
      >
        {vista.tipo === "tramite" && (
          <TramiteInfoPanel
            tramite={vista.tramite}
            onPreguntar={preguntarSobre}
            preguntarDeshabilitado={enviando}
          />
        )}
        {vista.tipo === "ambiguo" && (
          <TramitesAmbiguosPanel
            candidatos={vista.candidatos}
            onPreguntar={preguntarSobre}
            preguntarDeshabilitado={enviando}
          />
        )}
        {vista.tipo === "top3" && (
          <TramitesFrecuentesPanel
            tramites={vista.tramites}
            onPreguntar={preguntarSobre}
            preguntarDeshabilitado={enviando}
          />
        )}
      </aside>
    </div>
  );
}

function TabButton({
  activo,
  onClick,
  children,
}: {
  activo: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      className={`flex-1 p-3 text-sm font-medium ${
        activo ? "border-b-2 border-blue-600 text-blue-600" : "text-gray-500"
      }`}
      onClick={onClick}
    >
      {children}
    </button>
  );
}
```

- [ ] **Step 3: Correr el type-check y toda la suite de frontend**

Run: `cd frontend && npx tsc --noEmit && npm test -- --run`
Expected: PASS sin errores (type-check limpio, todos los tests de Vitest en verde).

- [ ] **Step 4: Verificación manual end-to-end**

Con el backend (`uvicorn agent.api:app --reload`) y el frontend (`npm run dev`) corriendo:

1. Abrir `http://localhost:3000` sin charla previa (sesión nueva) → el panel derecho muestra el top 3 global (o el placeholder de `TramitesFrecuentesPanel` si `veces_consultado` es 0 para todos).
2. Escribir "hola como hago una denuncia?" → el panel derecho muestra los candidatos ambiguos (nombre + descripción de la denuncia laboral y la de Defensa del Consumidor), sin que el chat repita esa info en el texto.
3. Hacer click en uno de los candidatos ambiguos → se envía "Quiero información sobre \<nombre\>." al chat, y el panel derecho pasa a mostrar el detalle completo de ese trámite.
4. Recargar la página en viewport mobile y confirmar que el tab "Info del trámite" sigue mostrando el estado correspondiente (top3 / ambiguo / tramite) sin romperse.

- [ ] **Step 5: Commit**

```bash
cd /home/seba/Escritorio/workspace/macacha
git add frontend/app/page.tsx frontend/components/TramiteInfoPanel.tsx
git commit -m "feat: elegir top3/ambiguo/tramite en el panel derecho según la charla"
```

---

## Self-Review Checklist (ya aplicado al escribir este plan)

- **Cobertura del spec:** top 3 global (Tasks 1-2), candidatos ambiguos en `"fin"` (Task 3), tipos y fetch frontend (Task 4), estado del panel (Task 5), componente de ambiguos (Task 6), reactivación clickeable de frecuentes (Task 7), wiring final (Task 8). Los 4 criterios de aceptación del spec quedan cubiertos por la verificación manual de Task 8 y los tests de Tasks 1-5.
- **Sin placeholders:** todos los pasos tienen código completo, ningún "TODO" ni "similar a la Task N".
- **Consistencia de tipos:** `VistaPanel`, `EstadoRelevante`, `CandidatoAmbiguo` y `TramiteFrecuente` se usan con los mismos nombres de campo en Tasks 4, 5, 6, 7 y 8 (`tramite_id`, `nombre_oficial`, `descripcion` / `veces_consultado`, `candidatosAmbiguos` en camelCase en el frontend vs. `candidatos_ambiguos` en snake_case solo en el JSON del SSE).
