"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { logout } from "../../lib/admin-api";
import { AdminAuthProvider, useAdminActual } from "../../hooks/useAdminActual";

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return (
    <AdminAuthProvider>
      <AdminLayoutInner>{children}</AdminLayoutInner>
    </AdminAuthProvider>
  );
}

function AdminLayoutInner({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const admin = useAdminActual();

  if (pathname === "/admin/login") {
    return <>{children}</>;
  }

  async function handleLogout() {
    await logout();
    router.push("/admin/login");
  }

  return (
    <div className="flex h-screen bg-gray-50 text-gray-900">
      <nav className="flex w-60 flex-none flex-col border-r border-gray-200 bg-white">
        <div className="flex items-center gap-3 border-b border-gray-200 px-4 py-4">
          <img
            src="/branding/macacha-icon.png"
            alt=""
            className="h-10 w-8 flex-none object-contain"
          />
          <div className="min-w-0">
            <p className="text-sm font-extrabold leading-tight">Macacha Admin</p>
            <p className="text-xs leading-tight text-gray-500">
              Gobierno de la Provincia de Salta
            </p>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto px-3 py-4">
          <p className="mb-2 px-2 text-xs font-extrabold uppercase tracking-widest text-gray-400">
            Operación
          </p>
          <ul className="space-y-1 text-sm">
            <li>
              <ItemNav href="/admin/chats" pathname={pathname} icono="◌">
                Chats
              </ItemNav>
            </li>
            <li>
              <ItemNav href="/admin/tramites" pathname={pathname} icono="✓">
                Trámites
              </ItemNav>
            </li>
            <li>
              <ItemNav href="/admin/contacto" pathname={pathname} icono="✦">
                Contacto
              </ItemNav>
            </li>
            <li>
              <ItemNav href="/admin/feedback" pathname={pathname} icono="★">
                Feedback
              </ItemNav>
            </li>
            {admin?.rol === "super_admin" && (
              <li>
                <ItemNav href="/admin/usuarios" pathname={pathname} icono="⚇">
                  Usuarios
                </ItemNav>
              </li>
            )}
          </ul>
        </div>

        <div className="grid gap-1 border-t border-gray-200 p-3">
          <Link
            href="/"
            className="flex min-h-[38px] items-center rounded-lg px-2.5 text-sm font-medium text-gray-500 hover:bg-gray-100 hover:text-gray-900"
          >
            Abrir chat
          </Link>
          <button
            onClick={handleLogout}
            className="flex min-h-[38px] items-center rounded-lg px-2.5 text-left text-sm font-medium text-gray-500 hover:bg-gray-100 hover:text-gray-900"
          >
            Cerrar sesión
          </button>
        </div>
      </nav>
      <main className="flex-1 overflow-y-auto">{children}</main>
    </div>
  );
}

function ItemNav({
  href,
  pathname,
  icono,
  children,
}: {
  href: string;
  pathname: string;
  icono: string;
  children: React.ReactNode;
}) {
  const activo = pathname.startsWith(href);
  return (
    <Link
      href={href}
      className={
        activo
          ? "flex min-h-[40px] items-center gap-2.5 rounded-lg bg-blue-50 px-2.5 font-semibold text-macacha-blueDark"
          : "flex min-h-[40px] items-center gap-2.5 rounded-lg px-2.5 text-gray-600 hover:bg-gray-50 hover:text-gray-900"
      }
    >
      <span className="w-5 text-center" aria-hidden="true">
        {icono}
      </span>
      {children}
    </Link>
  );
}
