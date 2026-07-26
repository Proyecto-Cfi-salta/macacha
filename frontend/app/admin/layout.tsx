"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { logout } from "../../lib/admin-api";

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();

  async function handleLogout() {
    await logout();
    router.push("/admin/login");
  }

  return (
    <div className="flex h-screen">
      <nav className="flex w-48 flex-col justify-between border-r border-gray-200 p-4">
        <div>
          <p className="mb-4 font-semibold">Macacha Admin</p>
          <ul className="space-y-2 text-sm">
            <li>
              <Link href="/admin/chats" className="text-blue-700 hover:underline">
                Chats
              </Link>
            </li>
            <li>
              <Link href="/admin/tramites" className="text-blue-700 hover:underline">
                Trámites
              </Link>
            </li>
          </ul>
        </div>
        <button onClick={handleLogout} className="text-left text-sm text-gray-500 hover:underline">
          Cerrar sesión
        </button>
      </nav>
      <main className="flex-1 overflow-y-auto">{children}</main>
    </div>
  );
}
