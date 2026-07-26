"use client";

export function ListaTextos({
  etiqueta,
  valores,
  onChange,
}: {
  etiqueta: string;
  valores: string[];
  onChange: (valores: string[]) => void;
}) {
  function actualizar(indice: number, valor: string) {
    const nuevos = [...valores];
    nuevos[indice] = valor;
    onChange(nuevos);
  }

  function agregar() {
    onChange([...valores, ""]);
  }

  function quitar(indice: number) {
    onChange(valores.filter((_, i) => i !== indice));
  }

  return (
    <div>
      <label className="mb-1 block text-sm font-medium">{etiqueta}</label>
      <div className="space-y-2">
        {valores.map((valor, indice) => (
          <div key={indice} className="flex gap-2">
            <input
              type="text"
              value={valor}
              onChange={(e) => actualizar(indice, e.target.value)}
              className="flex-1 rounded border border-gray-300 px-2 py-1 text-sm"
            />
            <button type="button" onClick={() => quitar(indice)} className="text-sm text-red-600">
              Quitar
            </button>
          </div>
        ))}
      </div>
      <button type="button" onClick={agregar} className="mt-2 text-sm text-blue-700 underline">
        + Agregar
      </button>
    </div>
  );
}
