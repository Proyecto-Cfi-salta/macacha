"use client";

import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { obtenerMe, type AdminSesionInfo } from "../lib/admin-api";

const AdminAuthContext = createContext<AdminSesionInfo | null>(null);

export function AdminAuthProvider({ children }: { children: ReactNode }) {
  const [admin, setAdmin] = useState<AdminSesionInfo | null>(null);

  useEffect(() => {
    obtenerMe().then(setAdmin);
  }, []);

  return <AdminAuthContext.Provider value={admin}>{children}</AdminAuthContext.Provider>;
}

export function useAdminActual(): AdminSesionInfo | null {
  return useContext(AdminAuthContext);
}
