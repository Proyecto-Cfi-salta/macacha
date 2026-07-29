# Macacha — Panel derecho como "caja de herramientas" (sub-proyecto D de 4)

## Contexto

Segundo de los 4 sub-proyectos para humanizar el chat (orden acordado:
A → D → B → C). **A** (personalidad/estilo del prompt) ya está completo.
Este documento cubre **D**: convertir el panel derecho (`TramiteInfoPanel.tsx`),
que hoy solo muestra texto estático (requisitos, costo/modalidad/duración,
pasos, enlaces oficiales, contacto), en algo interactivo y accionable.

## Qué cambia

Cuatro piezas interactivas nuevas, todas en el frontend, sin tocar el backend:

1. **Checklist tildable** en Requisitos y Pasos.
2. **Copiar con un click** en teléfono, email, y cada requisito/paso individual.
3. **Enlaces oficiales como botones destacados** en vez de links de texto.
4. **Botón "¿Tenés dudas?" por sección** (Requisitos, Costo/modalidad/duración,
   Pasos) que manda un mensaje pre-armado al chat automáticamente.

## Arquitectura y flujo de datos

### a) Checklist — hook nuevo `frontend/hooks/useChecklist.ts`

Persiste en `localStorage` por trámite (independiente de la sesión de chat,
que ya no persiste — ver `hooks/useSession.ts`). La lógica de armado de
claves y toggle se separa en funciones puras exportadas, testeables sin
renderizar nada (mismo patrón que `parsearLineasSSE` en `useChatStream.ts`).

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

### b) Botón "¿Tenés dudas?" — wiring entre `Chat` y `TramiteInfoPanel`

`TramiteInfoPanel` pasa a recibir dos props nuevas:

```typescript
onPreguntar: (mensaje: string) => void;
preguntarDeshabilitado: boolean;
```

En `app/page.tsx`, dentro de `Chat`, se arma así:

```typescript
function preguntarSobre(mensaje: string) {
  enviarMensaje(mensaje);
  setTab("chat");
}
```

y se pasa `onPreguntar={preguntarSobre}` y
`preguntarDeshabilitado={enviando}` a `TramiteInfoPanel`. `setTab("chat")`
solo importa en mobile (en desktop las tres columnas ya están visibles);
llamarlo igual en desktop no tiene efecto visual porque ahí `tab` no
condiciona el layout.

`preguntarDeshabilitado` evita que se dispare un segundo `enviarMensaje`
mientras uno anterior sigue en curso — `useChatStream.enviarMensaje` asume
un solo envío a la vez (agrega al último mensaje del array).

## Componentes nuevos

### `frontend/components/CopyButton.tsx`

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

### `frontend/components/TramiteInfoPanel.tsx` (reescritura completa)

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

### `app/page.tsx` — cambios en `Chat`

Se agrega `preguntarSobre` (arriba) y se actualiza el render de
`TramiteInfoPanel`:

```typescript
<TramiteInfoPanel
  tramite={tramite}
  onPreguntar={preguntarSobre}
  preguntarDeshabilitado={enviando}
/>
```

## Testing

**Automatizado (vitest, sin React Testing Library — no hay entorno de
render configurado en este proyecto):**
- `hooks/useChecklist.test.ts`: testea las funciones puras exportadas
  (`claveChecklist`, `claveItem`, `toggleItem`) — ej. togglear una clave la
  prende sin afectar las demás, togglear dos veces vuelve al estado
  original, `claveChecklist`/`claveItem` arman el string esperado.
- `TramiteInfoPanel.tsx`, `CopyButton.tsx`: sin test automatizado (mismo
  criterio ya usado en el proyecto para componentes de render puro).

**Manual (limitación: no hay herramienta de browser en este entorno):**
se verifica lo que es verificable sin browser — `tsc --noEmit`, los tests
de `useChecklist`, y que el bundle servido por Next.js contenga el código
nuevo (mismo método usado para verificar el sub-proyecto anterior). La
interacción real — tildar checkboxes, copiar al portapapeles, que el botón
de dudas mande el mensaje y cambie de tab en mobile — requiere que el
usuario la pruebe en su propio navegador antes de dar por cerrado el
sub-proyecto.

## Casos borde

- **Cambiar de trámite:** `useChecklist` re-lee `localStorage` cuando
  cambia `tramiteId` (efecto con `[tramiteId]` como dependencia) — el
  checklist de un trámite no se mezcla con el de otro.
- **`tramite` es `null`:** el panel muestra el placeholder actual, sin
  checklist ni botones (comportamiento ya existente, sin cambios).
- **Clipboard falla** (navegador sin soporte / contexto no seguro):
  `try/catch` en `CopyButton`; si falla, muestra "No se pudo copiar" en vez
  de romper.
- **Botón "¿Tenés dudas?" mientras el chat está enviando:** deshabilitado
  vía `preguntarDeshabilitado`.
- **`localStorage` con JSON corrupto** (editado a mano, etc.): no está en
  alcance manejarlo con un try/catch defensivo — es un caso extremadamente
  raro (nadie más que el propio usuario técnico edita esa clave) y ya es el
  criterio implícito usado en `useSession.ts` para su propia clave.

## Fuera de alcance

- Streaming real token-a-token (sub-proyecto B, pendiente).
- Memoria conversacional más inteligente (sub-proyecto C, pendiente).
- Sincronizar el checklist con el backend / entre dispositivos — queda
  puramente local al navegador.
- Botón de duda por ítem individual (se descartó a favor de uno por
  sección).
- Sección de Enlaces oficiales o Contacto con checklist — el checklist es
  solo para Requisitos y Pasos.

## Criterios de aceptación

- Tildar un requisito o paso lo marca visualmente (tachado) y persiste si
  se refresca la página, mientras se consulte el mismo trámite.
- Cambiar a un trámite distinto no arrastra el checklist del anterior.
- Cada requisito, paso, teléfono y email tiene un botón de copiar que
  copia el texto exacto al portapapeles.
- Los enlaces oficiales se muestran como botones con borde, no como texto
  subrayado.
- Cada una de las secciones Requisitos, Costo/modalidad/duración y Pasos
  tiene un botón "¿Tenés dudas sobre esto?" que manda el mensaje pre-armado
  correspondiente al chat automáticamente y (en mobile) cambia a la tab de
  Chat.
- El botón de dudas está deshabilitado mientras el chat está respondiendo.
