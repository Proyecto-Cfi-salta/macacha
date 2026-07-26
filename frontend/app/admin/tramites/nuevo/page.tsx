"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { TramiteForm } from "../../../../components/TramiteForm";
import {
  crearTramite,
  listarOrganismos,
  type TramiteDetalleAdmin,
} from "../../../../lib/admin-tramites-api";

const VALORES_VACIOS: TramiteDetalleAdmin = {
  organismo: "",
  categoria: "",
  nombre_oficial: "",
  descripcion: "",
  objetivo: "",
  requisitos: [],
  pasos: [],
  costo: "",
  modalidad: "",
  duracion: "",
  telefono_contacto: "",
  email_contacto: "",
  problemas_frecuentes: [],
  sinonimos: [],
  keywords: [],
  enlaces_oficiales: [],
  preguntas_frecuentes: [],
};

export default function NuevoTramitePage() {
  const router = useRouter();
  const [organismos, setOrganismos] = useState<string[]>([]);
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listarOrganismos()
      .then(setOrganismos)
      .catch(() => setOrganismos([]));
  }, []);

  async function handleGuardar(datos: TramiteDetalleAdmin) {
    setGuardando(true);
    setError(null);
    try {
      const resultado = await crearTramite(datos);
      router.push(`/admin/tramites/${resultado.tramite_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo guardar el trámite");
    } finally {
      setGuardando(false);
    }
  }

  return (
    <TramiteForm
      valoresIniciales={VALORES_VACIOS}
      organismosExistentes={organismos}
      guardando={guardando}
      error={error}
      onGuardar={handleGuardar}
    />
  );
}
