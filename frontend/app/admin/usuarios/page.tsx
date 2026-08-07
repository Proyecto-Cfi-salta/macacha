"use client";

import { useEffect, useState } from "react";
import { UsuarioForm } from "../../../components/UsuarioForm";
import { listarOrganismos, type Organismo } from "../../../lib/admin-tramites-api";
import {
  crearOrganismo,
  crearUsuario,
  editarUsuario,
  obtenerUsuarios,
  type AdminUsuario,
  type UsuarioFormValores,
} from "../../../lib/admin-usuarios-api";

const VALORES_VACIOS: UsuarioFormValores = {
  email: "",
  password: "",
  rol: "admin_organismo",
  organismo_id: null,
  activo: true,
};

export default function UsuariosPage() {
  const [usuarios, setUsuarios] = useState<AdminUsuario[] | null>(null);
  const [organismos, setOrganismos] = useState<Organismo[]>([]);
  const [error, setError] = useState(false);
  const [cargando, setCargando] = useState(true);
  const [editando, setEditando] = useState<AdminUsuario | "nuevo" | null>(null);
  const [guardando, setGuardando] = useState(false);
  const [errorGuardado, setErrorGuardado] = useState<string | null>(null);
  const [nombreOrganismoNuevo, setNombreOrganismoNuevo] = useState("");
  const [errorOrganismo, setErrorOrganismo] = useState<string | null>(null);

  useEffect(() => {
    cargar();
  }, []);

  async function cargar() {
    setCargando(true);
    setError(false);
    try {
      const [listaUsuarios, listaOrganismos] = await Promise.all([
        obtenerUsuarios(),
        listarOrganismos(),
      ]);
      setUsuarios(listaUsuarios);
      setOrganismos(listaOrganismos);
    } catch {
      setError(true);
    } finally {
      setCargando(false);
    }
  }

  async function handleCrearOrganismo() {
    if (!nombreOrganismoNuevo.trim()) return;
    setErrorOrganismo(null);
    try {
      await crearOrganismo(nombreOrganismoNuevo.trim());
      setNombreOrganismoNuevo("");
      setOrganismos(await listarOrganismos());
    } catch (err) {
      setErrorOrganismo(err instanceof Error ? err.message : "No se pudo crear el organismo");
    }
  }

  async function handleGuardar(datos: UsuarioFormValores) {
    setGuardando(true);
    setErrorGuardado(null);
    try {
      if (editando === "nuevo") {
        await crearUsuario(datos);
      } else if (editando) {
        await editarUsuario(editando.id, datos);
      }
      setEditando(null);
      await cargar();
    } catch (err) {
      setErrorGuardado(err instanceof Error ? err.message : "No se pudo guardar el usuario");
    } finally {
      setGuardando(false);
    }
  }

  function valoresParaEditar(usuario: AdminUsuario): UsuarioFormValores {
    return {
      email: usuario.email,
      password: "",
      rol: usuario.rol,
      organismo_id: organismos.find((o) => o.nombre === usuario.organismo)?.id ?? null,
      activo: usuario.activo,
    };
  }

  if (cargando) {
    return <p className="p-4 text-sm text-gray-500">Cargando…</p>;
  }

  if (error) {
    return (
      <div className="p-4">
        <p className="text-sm text-red-600">No se pudo cargar la lista de usuarios</p>
        <button onClick={cargar} className="mt-2 text-sm text-blue-700 underline">
          Reintentar
        </button>
      </div>
    );
  }

  return (
    <div className="p-4">
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-lg font-semibold">Usuarios</h1>
        <button
          onClick={() => setEditando("nuevo")}
          className="rounded bg-blue-600 px-3 py-1.5 text-sm text-white"
        >
          Nuevo usuario
        </button>
      </div>

      <div className="mb-4 flex items-end gap-2">
        <div>
          <label className="mb-1 block text-sm font-medium">Nuevo organismo</label>
          <input
            type="text"
            value={nombreOrganismoNuevo}
            onChange={(e) => setNombreOrganismoNuevo(e.target.value)}
            className="rounded border border-gray-300 px-2 py-1 text-sm"
          />
        </div>
        <button onClick={handleCrearOrganismo} className="rounded bg-gray-200 px-3 py-1.5 text-sm">
          Crear organismo
        </button>
        {errorOrganismo && <p className="text-sm text-red-600">{errorOrganismo}</p>}
      </div>

      {editando && (
        <div className="mb-4">
          <UsuarioForm
            key={editando === "nuevo" ? "nuevo" : editando.id}
            valoresIniciales={editando === "nuevo" ? VALORES_VACIOS : valoresParaEditar(editando)}
            organismos={organismos}
            esEdicion={editando !== "nuevo"}
            guardando={guardando}
            error={errorGuardado}
            onGuardar={handleGuardar}
            onCancelar={() => setEditando(null)}
          />
        </div>
      )}

      {usuarios && usuarios.length === 0 ? (
        <p className="text-sm text-gray-500">Todavía no hay usuarios cargados</p>
      ) : (
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-200 text-left">
              <th className="p-2">Email</th>
              <th className="p-2">Rol</th>
              <th className="p-2">Organismo</th>
              <th className="p-2">Activo</th>
              <th className="p-2"></th>
            </tr>
          </thead>
          <tbody>
            {usuarios!.map((usuario) => (
              <tr key={usuario.id} className="border-b border-gray-100">
                <td className="p-2">{usuario.email}</td>
                <td className="p-2">
                  {usuario.rol === "super_admin" ? "Super admin" : "Admin de organismo"}
                </td>
                <td className="p-2">{usuario.organismo ?? "—"}</td>
                <td className="p-2">{usuario.activo ? "Sí" : "No"}</td>
                <td className="p-2">
                  <button
                    onClick={() => setEditando(usuario)}
                    className="text-sm text-blue-700 underline"
                  >
                    Editar
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
