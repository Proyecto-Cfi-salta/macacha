"use client";

import { useState, type FormEvent } from "react";
import type { Organismo } from "../lib/admin-tramites-api";
import type { UsuarioFormValores } from "../lib/admin-usuarios-api";
import { CampoContrasena } from "./CampoContrasena";

export function UsuarioForm({
  valoresIniciales,
  organismos,
  esEdicion,
  guardando,
  error,
  onGuardar,
  onCancelar,
}: {
  valoresIniciales: UsuarioFormValores;
  organismos: Organismo[];
  esEdicion: boolean;
  guardando: boolean;
  error: string | null;
  onGuardar: (datos: UsuarioFormValores) => void;
  onCancelar: () => void;
}) {
  const [datos, setDatos] = useState<UsuarioFormValores>(valoresIniciales);

  function actualizar<K extends keyof UsuarioFormValores>(campo: K, valor: UsuarioFormValores[K]) {
    setDatos((anterior) => ({ ...anterior, [campo]: valor }));
  }

  function handleSubmit(evento: FormEvent) {
    evento.preventDefault();
    onGuardar(datos);
  }

  const puedeGuardar =
    datos.email.trim() !== "" &&
    (esEdicion || datos.password.trim().length >= 8) &&
    (datos.rol === "super_admin" || datos.organismo_id !== null);

  return (
    <form onSubmit={handleSubmit} className="tarjeta max-w-md space-y-3">
      <div>
        <label className="campo-label">Email</label>
        <input
          type="email"
          value={datos.email}
          disabled={esEdicion}
          onChange={(e) => actualizar("email", e.target.value)}
          className="campo-input w-full"
        />
      </div>

      <div>
        <label className="campo-label">
          {esEdicion ? "Nueva contraseña (dejar en blanco para no cambiar)" : "Contraseña"}
        </label>
        <CampoContrasena
          value={datos.password}
          onChange={(e) => actualizar("password", e.target.value)}
          className="campo-input w-full"
        />
      </div>

      <div>
        <label className="campo-label">Rol</label>
        <select
          value={datos.rol}
          onChange={(e) => actualizar("rol", e.target.value as UsuarioFormValores["rol"])}
          className="campo-input w-full"
        >
          <option value="admin_organismo">Admin de organismo</option>
          <option value="super_admin">Super admin</option>
        </select>
      </div>

      {datos.rol === "admin_organismo" && (
        <div>
          <label className="campo-label">Organismo</label>
          <select
            value={datos.organismo_id ?? ""}
            onChange={(e) => actualizar("organismo_id", e.target.value ? Number(e.target.value) : null)}
            className="campo-input w-full"
          >
            <option value="">Elegir…</option>
            {organismos.map((organismo) => (
              <option key={organismo.id} value={organismo.id}>
                {organismo.nombre}
              </option>
            ))}
          </select>
        </div>
      )}

      {esEdicion && (
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={datos.activo}
            onChange={(e) => actualizar("activo", e.target.checked)}
          />
          Activo
        </label>
      )}

      {error && <p className="text-sm texto-error">{error}</p>}

      <div className="flex gap-2">
        <button type="submit" disabled={!puedeGuardar || guardando} className="boton-primario">
          {guardando ? "Guardando…" : "Guardar"}
        </button>
        <button type="button" onClick={onCancelar} className="boton-neutro">
          Cancelar
        </button>
      </div>
    </form>
  );
}
