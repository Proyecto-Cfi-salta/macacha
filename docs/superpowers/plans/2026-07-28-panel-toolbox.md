# Panel derecho como "caja de herramientas" (sub-proyecto D) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convertir el panel derecho (`TramiteInfoPanel.tsx`) en interactivo: checklist tildable en requisitos/pasos, copiar con un click, enlaces oficiales como botones, y un botón "¿Tenés dudas?" por sección que manda un mensaje pre-armado al chat.

**Architecture:** Un hook nuevo (`useChecklist`) con lógica pura testeable, un componente nuevo (`CopyButton`), una reescritura de `TramiteInfoPanel.tsx`, y wiring nuevo en `app/page.tsx` para pasarle al panel una función que manda mensajes al chat. Sin cambios de backend.

**Tech Stack:** Next.js 15 / React 19 / TypeScript, Tailwind, vitest (sin React Testing Library — no hay entorno de render configurado en este proyecto).

## Global Constraints

- Ningún cambio de backend — este sub-proyecto es 100% frontend.
- El checklist persiste en `localStorage` bajo la clave `macacha_checklist_${tramiteId}` — independiente de la sesión de chat (que ya NO persiste, ver `hooks/useSession.ts`).
- Solo se testean con vitest las funciones puras (`claveChecklist`, `claveItem`, `toggleItem` de `useChecklist.ts`). `CopyButton.tsx` y `TramiteInfoPanel.tsx` no llevan test automatizado (no hay React Testing Library en este proyecto — criterio ya usado para componentes de render puro).
- El botón "¿Tenés dudas?" existe solo en 3 secciones: Requisitos, Costo/modalidad/duración, Pasos. No en Enlaces oficiales ni Contacto.
- El checklist (checkbox + tachado) existe solo en Requisitos y Pasos. Enlaces oficiales y Contacto no llevan checklist.
- Sin herramienta de browser en este entorno: la verificación final de interacción real (tildar, copiar, cambio de tab en mobile) la hace el usuario en su propio navegador — no se puede automatizar acá.

---

### Task 1: Hook `useChecklist` con funciones puras y tests

**Files:**
- Create: `frontend/hooks/useChecklist.ts`
- Test: `frontend/hooks/useChecklist.test.ts`

**Interfaces:**
- Consumes: nada (hook nuevo, sin dependencias del resto del proyecto salvo `react`).
- Produces: `useChecklist(tramiteId: string | null)` retorna `{ estaTildado(tipo, indice): boolean, toggle(tipo, indice): void }`. `TipoItemChecklist = "requisito" | "paso"`. Funciones puras exportadas: `claveChecklist(tramiteId: string): string`, `claveItem(tipo: TipoItemChecklist, indice: number): string`, `toggleItem(estado: Record<string, boolean>, clave: string): Record<string, boolean>`. Task 3 (`TramiteInfoPanel.tsx`) consume `useChecklist`, `estaTildado` y `toggle` con esta firma exacta.

- [ ] **Step 1: Escribir los tests de las funciones puras**

Crear `frontend/hooks/useChecklist.test.ts`:

```typescript
import { describe, expect, it } from "vitest";
import { claveChecklist, claveItem, toggleItem } from "./useChecklist";

describe("claveChecklist", () => {
  it("arma la clave de localStorage a partir del tramite_id", () => {
    expect(claveChecklist("RC-0004")).toBe("macacha_checklist_RC-0004");
  });
});

describe("claveItem", () => {
  it("arma la clave de un requisito por índice", () => {
    expect(claveItem("requisito", 0)).toBe("requisito:0");
  });

  it("arma la clave de un paso por índice", () => {
    expect(claveItem("paso", 2)).toBe("paso:2");
  });
});

describe("toggleItem", () => {
  it("prende una clave que no estaba en el estado", () => {
    expect(toggleItem({}, "requisito:0")).toEqual({ "requisito:0": true });
  });

  it("apaga una clave que estaba prendida", () => {
    expect(toggleItem({ "requisito:0": true }, "requisito:0")).toEqual({
      "requisito:0": false,
    });
  });

  it("no afecta otras claves del estado", () => {
    const estado = { "requisito:0": true, "paso:1": true };
    expect(toggleItem(estado, "requisito:0")).toEqual({
      "requisito:0": false,
      "paso:1": true,
    });
  });
});
```

- [ ] **Step 2: Correr los tests y verificar que fallan**

Run: `cd frontend && npx vitest run hooks/useChecklist.test.ts`
Expected: FAIL — `useChecklist.ts` todavía no existe (error de módulo no encontrado).

- [ ] **Step 3: Implementar `useChecklist.ts`**

Crear `frontend/hooks/useChecklist.ts`:

```typescript
"use client";

import { useEffect, useState } from "react";

export type TipoItemChecklist = "requisito" | "paso";

export function claveChecklist(tramiteId: string): string {
  return `macacha_checklist_${tramiteId}`;
}

export function claveItem(tipo: TipoItemChecklist, indice: number): string {
  return `${tipo}:${indice}`;
}

export function toggleItem(
  estado: Record<string, boolean>,
  clave: string
): Record<string, boolean> {
  return { ...estado, [clave]: !estado[clave] };
}

export function useChecklist(tramiteId: string | null) {
  const [estado, setEstado] = useState<Record<string, boolean>>({});

  useEffect(() => {
    if (!tramiteId) {
      setEstado({});
      return;
    }
    const guardado = localStorage.getItem(claveChecklist(tramiteId));
    setEstado(guardado ? JSON.parse(guardado) : {});
  }, [tramiteId]);

  function toggle(tipo: TipoItemChecklist, indice: number) {
    if (!tramiteId) return;
    setEstado((prev) => {
      const nuevo = toggleItem(prev, claveItem(tipo, indice));
      localStorage.setItem(claveChecklist(tramiteId), JSON.stringify(nuevo));
      return nuevo;
    });
  }

  function estaTildado(tipo: TipoItemChecklist, indice: number): boolean {
    return Boolean(estado[claveItem(tipo, indice)]);
  }

  return { estaTildado, toggle };
}
```

- [ ] **Step 4: Correr los tests y verificar que pasan**

Run: `cd frontend && npx vitest run hooks/useChecklist.test.ts`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add frontend/hooks/useChecklist.ts frontend/hooks/useChecklist.test.ts
git commit -m "feat: agregar hook useChecklist para tildar requisitos/pasos"
```

---

### Task 2: `CopyButton` + reescritura de `TramiteInfoPanel` + wiring en `page.tsx`

**Files:**
- Create: `frontend/components/CopyButton.tsx`
- Modify: `frontend/components/TramiteInfoPanel.tsx` (reescritura completa)
- Modify: `frontend/app/page.tsx`

**Interfaces:**
- Consumes: `useChecklist` de Task 1 (`estaTildado`, `toggle` con la firma ya definida). `TramiteDetalle` de `frontend/lib/api.ts` (sin cambios, ya tiene los 12 campos).
- Produces: `TramiteInfoPanel` pasa a requerir dos props nuevas — `onPreguntar: (mensaje: string) => void` y `preguntarDeshabilitado: boolean` — que `app/page.tsx` debe proveer.

- [ ] **Step 1: Crear `CopyButton.tsx`**

Crear `frontend/components/CopyButton.tsx`:

```typescript
"use client";

import { useState } from "react";

export function CopyButton({ texto }: { texto: string }) {
  const [estado, setEstado] = useState<"idle" | "copiado" | "error">("idle");

  async function copiar() {
    try {
      await navigator.clipboard.writeText(texto);
      setEstado("copiado");
    } catch {
      setEstado("error");
    }
    setTimeout(() => setEstado("idle"), 1500);
  }

  return (
    <button
      type="button"
      onClick={copiar}
      className="ml-2 text-xs text-blue-700 underline"
      aria-label={`Copiar ${texto}`}
    >
      {estado === "idle" && "Copiar"}
      {estado === "copiado" && "Copiado ✓"}
      {estado === "error" && "No se pudo copiar"}
    </button>
  );
}
```

- [ ] **Step 2: Reescribir `TramiteInfoPanel.tsx`**

Reemplazar todo el contenido de `frontend/components/TramiteInfoPanel.tsx` por:

```typescript
"use client";

import type { TramiteDetalle } from "../lib/api";
import { CopyButton } from "./CopyButton";
import { useChecklist } from "../hooks/useChecklist";

export function TramiteInfoPanel({
  tramite,
  onPreguntar,
  preguntarDeshabilitado,
}: {
  tramite: TramiteDetalle | null;
  onPreguntar: (mensaje: string) => void;
  preguntarDeshabilitado: boolean;
}) {
  const { estaTildado, toggle } = useChecklist(tramite?.tramite_id ?? null);

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
          <ul className="mt-1 space-y-1 text-sm">
            {tramite.requisitos.map((requisito, indice) => (
              <li key={requisito} className="flex items-start gap-2">
                <input
                  type="checkbox"
                  className="mt-1"
                  checked={estaTildado("requisito", indice)}
                  onChange={() => toggle("requisito", indice)}
                  aria-label={`Marcar requisito: ${requisito}`}
                />
                <span
                  className={
                    estaTildado("requisito", indice)
                      ? "flex-1 line-through text-gray-400"
                      : "flex-1"
                  }
                >
                  {requisito}
                </span>
                <CopyButton texto={requisito} />
              </li>
            ))}
          </ul>
          <BotonDuda
            texto={`Tengo una duda sobre los requisitos de ${tramite.nombre_oficial}.`}
            onPreguntar={onPreguntar}
            disabled={preguntarDeshabilitado}
          />
        </div>
      )}

      {(tramite.costo || tramite.modalidad || tramite.duracion) && (
        <div className="mt-4 text-sm">
          <h3 className="font-medium">Costo, modalidad y duración</h3>
          {tramite.costo && <p>Costo: {tramite.costo}</p>}
          {tramite.modalidad && <p>Modalidad: {tramite.modalidad}</p>}
          {tramite.duracion && <p>Duración: {tramite.duracion}</p>}
          <BotonDuda
            texto={`Tengo una duda sobre el costo, la modalidad o la duración de ${tramite.nombre_oficial}.`}
            onPreguntar={onPreguntar}
            disabled={preguntarDeshabilitado}
          />
        </div>
      )}

      {tramite.pasos.length > 0 && (
        <div className="mt-4">
          <h3 className="text-sm font-medium">Pasos</h3>
          <ol className="mt-1 space-y-1 text-sm">
            {tramite.pasos.map((paso, indice) => (
              <li key={paso} className="flex items-start gap-2">
                <input
                  type="checkbox"
                  className="mt-1"
                  checked={estaTildado("paso", indice)}
                  onChange={() => toggle("paso", indice)}
                  aria-label={`Marcar paso: ${paso}`}
                />
                <span
                  className={
                    estaTildado("paso", indice)
                      ? "flex-1 line-through text-gray-400"
                      : "flex-1"
                  }
                >
                  {paso}
                </span>
                <CopyButton texto={paso} />
              </li>
            ))}
          </ol>
          <BotonDuda
            texto={`Tengo una duda sobre los pasos de ${tramite.nombre_oficial}.`}
            onPreguntar={onPreguntar}
            disabled={preguntarDeshabilitado}
          />
        </div>
      )}

      {tramite.enlaces_oficiales.length > 0 && (
        <div className="mt-4">
          <h3 className="text-sm font-medium">Enlaces oficiales</h3>
          <div className="mt-1 flex flex-col gap-2">
            {tramite.enlaces_oficiales.map((enlace) => (
              <a
                key={enlace}
                href={enlace}
                target="_blank"
                rel="noreferrer"
                className="rounded border border-blue-600 px-3 py-1.5 text-center text-sm text-blue-700 hover:bg-blue-50"
              >
                {enlace}
              </a>
            ))}
          </div>
        </div>
      )}

      <div className="mt-4 text-sm">
        <h3 className="font-medium">Contacto</h3>
        {tramite.telefono_contacto && (
          <p>
            Tel: {tramite.telefono_contacto}
            <CopyButton texto={tramite.telefono_contacto} />
          </p>
        )}
        {tramite.email_contacto && (
          <p>
            Mail: {tramite.email_contacto}
            <CopyButton texto={tramite.email_contacto} />
          </p>
        )}
        {!tramite.telefono_contacto && !tramite.email_contacto && (
          <p className="text-gray-400">Sin datos de contacto.</p>
        )}
      </div>
    </div>
  );
}

function BotonDuda({
  texto,
  onPreguntar,
  disabled,
}: {
  texto: string;
  onPreguntar: (mensaje: string) => void;
  disabled: boolean;
}) {
  return (
    <button
      type="button"
      onClick={() => onPreguntar(texto)}
      disabled={disabled}
      className="mt-2 text-xs text-blue-700 underline disabled:opacity-50"
    >
      ¿Tenés dudas sobre esto?
    </button>
  );
}
```

- [ ] **Step 3: Wiring en `app/page.tsx`**

En `frontend/app/page.tsx`, dentro de la función `Chat` (después de la línea
`const [tab, setTab] = useState<Tab>("chat");`), agregar:

```typescript
function preguntarSobre(mensaje: string) {
  enviarMensaje(mensaje);
  setTab("chat");
}
```

Y reemplazar el uso actual de `<TramiteInfoPanel tramite={tramite} />` por:

```typescript
<TramiteInfoPanel
  tramite={tramite}
  onPreguntar={preguntarSobre}
  preguntarDeshabilitado={enviando}
/>
```

- [ ] **Step 4: Verificar tipos**

Run: `cd frontend && npx tsc --noEmit`
Expected: sin errores.

- [ ] **Step 5: Correr toda la suite de tests del frontend**

Run: `cd frontend && npm test`
Expected: todos los tests pasan (incluye los 5 nuevos de `useChecklist.test.ts` más los ya existentes de `useChatStream.test.ts` y `lib/admin-chats.test.ts`).

- [ ] **Step 6: Commit**

```bash
git add frontend/components/CopyButton.tsx frontend/components/TramiteInfoPanel.tsx frontend/app/page.tsx
git commit -m "feat: panel del trámite interactivo (checklist, copiar, enlaces como botones, botón de dudas)"
```

---

### Task 3: Verificación manual

**Files:** ninguno (solo verificación).

**Interfaces:**
- Consumes: backend real corriendo, frontend real corriendo (`npm run dev`), navegador del usuario (no hay herramienta de browser en este entorno de ejecución).

- [ ] **Step 1: Confirmar que el bundle servido contiene el código nuevo**

Con el frontend corriendo (`npm run dev` en :3000), confirmar que Next.js
compiló el cambio:

Run:
```bash
curl -s "http://localhost:3000/" -o /tmp/home.html
grep -oE 'src="[^"]*chunks/app/page\.js[^"]*"' /tmp/home.html
curl -s "http://localhost:3000/_next/static/chunks/app/page.js" -o /tmp/page.js
grep -o "Tenés dudas sobre esto" /tmp/page.js
```
Expected: encuentra la frase "¿Tenés dudas sobre esto?" en el bundle
servido (confirma que el código nuevo está compilado y disponible, aunque
no se pueda interactuar con él sin browser).

- [ ] **Step 2: Pedirle al usuario que verifique la interacción real en su navegador**

Como este entorno no tiene herramienta de browser, este paso NO se puede
automatizar. Pedirle al usuario que abra `http://localhost:3000`, identifique
un trámite (ej. preguntando por "seguimiento de mi acta" o cualquier trámite
real), y confirme:

- Tildar un requisito/paso lo tacha visualmente.
- Refrescar la página y volver a preguntar por el mismo trámite mantiene lo
  tildado.
- El botón "Copiar" junto a un requisito, paso, teléfono o email copia el
  texto (pegarlo en algún lado para confirmar).
- Los enlaces oficiales se ven como botones con borde, no como texto
  subrayado.
- Tocar "¿Tenés dudas sobre esto?" manda el mensaje al chat automáticamente
  sin que haga falta tocar "Enviar", y (si está en mobile) cambia a la tab
  de Chat.

- [ ] **Step 3: Reportar resultado**

Si el usuario confirma los 5 puntos, marcar la tarea como completa. Si algo
falla, documentar el caso concreto y decidir el ajuste antes de cerrar el
sub-proyecto D.
