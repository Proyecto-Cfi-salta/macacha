export function tipoCampoContrasena(visible: boolean): "text" | "password" {
  return visible ? "text" : "password";
}

export function etiquetaVerContrasena(visible: boolean): string {
  return visible ? "Ocultar contraseña" : "Mostrar contraseña";
}
