"use client";

import type { Faq } from "../lib/admin-tramites-api";

export function ListaFAQ({
  valores,
  onChange,
}: {
  valores: Faq[];
  onChange: (valores: Faq[]) => void;
}) {
  function actualizar(indice: number, campo: keyof Faq, valor: string) {
    const nuevos = [...valores];
    nuevos[indice] = { ...nuevos[indice], [campo]: valor };
    onChange(nuevos);
  }

  function agregar() {
    onChange([...valores, { pregunta: "", respuesta: "" }]);
  }

  function quitar(indice: number) {
    onChange(valores.filter((_, i) => i !== indice));
  }

  return (
    <div>
      <label className="mb-1 block text-sm font-medium">Preguntas frecuentes</label>
      <div className="space-y-3">
        {valores.map((faq, indice) => (
          <div key={indice} className="space-y-1 rounded border border-gray-200 p-2">
            <input
              type="text"
              placeholder="Pregunta"
              value={faq.pregunta}
              onChange={(e) => actualizar(indice, "pregunta", e.target.value)}
              className="w-full rounded border border-gray-300 px-2 py-1 text-sm"
            />
            <input
              type="text"
              placeholder="Respuesta"
              value={faq.respuesta}
              onChange={(e) => actualizar(indice, "respuesta", e.target.value)}
              className="w-full rounded border border-gray-300 px-2 py-1 text-sm"
            />
            <button type="button" onClick={() => quitar(indice)} className="text-sm text-red-600">
              Quitar
            </button>
          </div>
        ))}
      </div>
      <button type="button" onClick={agregar} className="mt-2 text-sm text-blue-700 underline">
        + Agregar pregunta
      </button>
    </div>
  );
}
