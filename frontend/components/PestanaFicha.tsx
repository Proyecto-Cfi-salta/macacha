// Pestaña pegada al borde derecho para abrir la ficha en pantallas angostas.
// En escritorio la ficha ya está a la vista, así que no se muestra.
export function PestanaFicha({ onAbrir }: { onAbrir: () => void }) {
  return (
    <button
      type="button"
      onClick={onAbrir}
      aria-label="Ver ficha del trámite"
      className="fixed right-0 top-1/2 z-40 flex -translate-y-1/2 flex-col items-center gap-2 rounded-l-xl border border-r-0 border-white/20 bg-macacha-navy px-1.5 py-3 text-white shadow-lg min-[1051px]:hidden"
    >
      <svg
        aria-hidden="true"
        viewBox="0 0 24 24"
        className="h-5 w-5"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" />
        <path d="M14 3v5h5M9 13h6M9 17h6" />
      </svg>
      <span className="text-xs font-bold tracking-wide [writing-mode:vertical-rl]">Ficha</span>
    </button>
  );
}
