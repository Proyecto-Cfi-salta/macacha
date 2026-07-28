# Macacha — Tono cálido del chat + más datos duros en el panel derecho

## Contexto

Dos ajustes chicos y relacionados al frontend de tres columnas
(`2026-07-22-paneles-laterales-design.md`):

1. El `SYSTEM_PROMPT` del agente (`backend/agent/orchestrator.py`) es
   puramente funcional, sin ninguna guía de tono — y además menciona
   explícitamente "Registro Civil" como si fuera el único organismo
   cargado, lo cual quedó desactualizado ahora que también hay trámites de
   Defensa del Consumidor y Secretaría de Trabajo.
2. El panel derecho (`TramiteInfoPanel.tsx`) solo muestra nombre oficial,
   organismo, requisitos y contacto — falta costo, modalidad, duración,
   pasos y enlaces oficiales, que ya están en el snapshot de cada trámite
   pero hoy solo se consiguen preguntándole al chat.

## System prompt — tono cálido y sin organismos hardcodeados

`backend/agent/orchestrator.py`'s `SYSTEM_PROMPT` pasa de:

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

a (texto aprobado tal cual con el usuario durante el brainstorming):

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

**Por qué no se menciona ningún organismo específico**: el prompt anterior
decía "Hoy tenés información sobre trámites del Registro Civil", una lista
que se desactualiza cada vez que se ingieren datos de un organismo nuevo
(ya pasó una vez). El prompt nuevo no enumera organismos — `buscar_tramite`
ya está acotado a lo que realmente existe en la base, así que el agente no
necesita que se le diga qué cubre y qué no; simplemente encuentra o no
encuentra resultados. Esto también deja el prompt listo para cuando se
sigan cargando más organismos del gobierno de Salta a futuro, sin que haga
falta tocarlo de nuevo por esto.

**Se mantiene sin cambios**: la restricción de no inventar datos, el
comportamiento de desambiguación, y el uso del nombre oficial + enlace
oficial — son reglas de precisión, no de tono, y no tienen que ver con este
ajuste.

## Panel derecho — más datos duros

**Backend**: `GET /tramites/{tramite_id}` (endpoint público existente en
`backend/agent/api.py`) suma 5 campos a la respuesta, tomados del mismo
snapshot que ya lee:

```python
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

**Frontend**: `frontend/lib/api.ts`'s tipo `TramiteDetalle` suma los campos
correspondientes:

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

`frontend/components/TramiteInfoPanel.tsx` agrega tres secciones nuevas,
cada una condicional a que el dato no venga vacío (mismo criterio que ya
usa la sección de Requisitos y de Contacto):

- **Costo, modalidad y duración**: los tres juntos en una sola sección
  chica (son datos cortos de una línea cada uno), solo se muestran los que
  no estén vacíos.
- **Pasos**: lista numerada, mismo estilo visual que Requisitos pero con
  números en vez de viñetas.
- **Enlaces oficiales**: lista de links (`<a href target="_blank">`), igual
  criterio que los enlaces ya usados en `ChatMessage.tsx`/`BurbujaMensaje`.

El orden de las secciones en el panel queda: nombre/organismo (ya existe) →
Requisitos (ya existe) → Costo/modalidad/duración (nuevo) → Pasos (nuevo) →
Enlaces oficiales (nuevo) → Contacto (ya existe, al final).

## Testing

- **Backend**: test de que `GET /tramites/{id}` devuelve los 5 campos
  nuevos con los valores del snapshot; test de que si el snapshot no tiene
  alguno de esos campos (`.get()` con default), el endpoint no rompe y
  devuelve el default (`""` o `[]`).
- **Frontend**: sin test automatizado para el panel (mismo criterio que el
  resto del proyecto para componentes de UI sin lógica pura extraíble).
- **System prompt**: no es código con lógica testeable (es un string
  constante) — se verifica manualmente conversando con el chat real.

## Fuera de alcance

- Cambiar el tono de mensajes de error genéricos (`"Ocurrió un error al
  procesar tu mensaje."`) — siguen neutros, no llevan la personalidad del
  prompt.
- Mostrar `objetivo`/`descripcion` (lo que devuelve `obtener_normativa`) en
  el panel — es contenido más largo/explicativo, no encaja como "dato
  duro" de un vistazo; queda para si se pide más adelante.
- Cualquier cambio a `TramitesFrecuentesPanel.tsx` (panel izquierdo) — no
  se pidió tocarlo.
- Botón o mecanismo para que el admin edite el tono del prompt desde la UI
  (eso sería el "visor/editor del prompt del agente", una sección del panel
  de admin ya identificada como pendiente futura en una sesión anterior,
  no parte de este documento).

## Criterios de aceptación

- Preguntarle algo simple al chat (ej. "hola") devuelve una respuesta con
  tono cálido y cercano, no un texto robótico/neutro.
- Preguntar por un trámite de Defensa del Consumidor o Secretaría de
  Trabajo funciona igual de bien que uno de Registro Civil (confirma que
  sacar la mención hardcodeada de organismo no rompió nada).
- El panel derecho, al identificar un trámite, muestra costo, modalidad,
  duración, pasos y enlaces oficiales además de lo que ya mostraba.
- Un trámite cuyo snapshot no tenga alguno de esos campos (ej. sin
  `enlaces_oficiales`) no rompe el panel — esa sección simplemente no
  aparece.
