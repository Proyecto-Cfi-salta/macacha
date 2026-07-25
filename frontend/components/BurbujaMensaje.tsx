export function BurbujaMensaje({
  esUsuario,
  className = "",
  children,
}: {
  esUsuario: boolean;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div className={`flex ${esUsuario ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[80%] rounded-lg px-4 py-2 ${
          esUsuario ? "bg-blue-600 text-white" : "bg-gray-100 text-gray-900"
        } ${className}`}
      >
        {children}
      </div>
    </div>
  );
}
