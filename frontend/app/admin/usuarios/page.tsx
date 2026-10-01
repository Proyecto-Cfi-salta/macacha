"use client";

import { useEffect, useState } from "react";
import { UsuarioForm } from "../../../components/UsuarioForm";
import { listarOrganismos, type Organismo } from "../../../lib/admin-tramites-api";
import {
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
    return <p className="p-4 text-sm texto-secundario">Cargando…</p>;
  }

  if (error) {
    return (
      <div className="p-4">
        <p className="text-sm texto-error">No se pudo cargar la lista de usuarios</p>
        <button onClick={cargar} className="boton-secundario mt-2">
          Reintentar
        </button>
      </div>
    );
  }

  return (
    <div className="p-4">
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-lg font-semibold">Usuarios</h1>
        <button onClick={() => setEditando("nuevo")} className="boton-primario">
          Nuevo usuario
        </button>
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
        <p className="text-sm texto-secundario">Todavía no hay usuarios cargados</p>
      ) : (
        <table className="w-full text-sm">
          <thead>
            <tr className="tabla-cabecera">
              <th className="p-2">Email</th>
              <th className="p-2">Rol</th>
              <th className="p-2">Organismo</th>
              <th className="p-2">Activo</th>
              <th className="p-2"></th>
            </tr>
          </thead>
          <tbody>
            {usuarios!.map((usuario) => (
              <tr key={usuario.id} className="tabla-fila">
                <td className="p-2">{usuario.email}</td>
                <td className="p-2">
                  {usuario.rol === "super_admin" ? "Super admin" : "Admin de organismo"}
                </td>
                <td className="p-2">{usuario.organismo ?? "—"}</td>
                <td className="p-2">{usuario.activo ? "Sí" : "No"}</td>
                <td className="p-2">
                  <button onClick={() => setEditando(usuario)} className="boton-secundario">
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
