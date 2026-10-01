"use client";

import { useState, type FormEvent } from "react";
import { login } from "../../../lib/admin-api";
import { CampoContrasena } from "../../../components/CampoContrasena";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(false);
  const [enviando, setEnviando] = useState(false);

  async function handleSubmit(evento: FormEvent) {
    evento.preventDefault();
    setEnviando(true);
    setError(false);
    const resultado = await login(email, password);
    setEnviando(false);
    if (!resultado.ok) {
      setError(true);
      return;
    }
    // Recarga completa (no router.push): AdminAuthProvider (hooks/useAdminActual.tsx) solo pide
    // /admin/me al montarse, y como vive en el layout compartido de /admin/*, una navegación de
    // cliente no lo remonta — el menú "Usuarios" quedaba sin aparecer para un super_admin hasta
    // un F5. Forzar la recarga acá remonta el provider con la sesión ya autenticada.
    window.location.href = "/admin/chats";
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-50 p-4">
      <div className="w-full max-w-sm overflow-hidden rounded-3xl border border-gray-200 bg-white shadow-xl">
        <div className="bg-gradient-to-br from-macacha-blueDark to-macacha-blue p-6 text-center text-white">
          <img src="/branding/macacha-icon.png" alt="Macacha" className="mx-auto h-12 w-12" />
          <h1 className="mt-3 text-lg font-semibold">Ingresar</h1>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4 p-6">
          <input
            type="email"
            placeholder="Email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="campo-input w-full"
            required
          />
          <CampoContrasena
            placeholder="Contraseña"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="campo-input w-full"
            required
          />
          {error && <p className="text-sm texto-error">Credenciales inválidas</p>}
          <button type="submit" disabled={enviando} className="boton-primario w-full">
            {enviando ? "Ingresando…" : "Ingresar"}
          </button>
        </form>
      </div>
    </div>
  );
}
