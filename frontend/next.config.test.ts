import { describe, expect, it } from "vitest";
import nextConfig from "./next.config";

async function encabezados(): Promise<Record<string, string>> {
  const reglas = await nextConfig.headers!();
  expect(reglas).toHaveLength(1);
  expect(reglas[0].source).toBe("/:path*");
  return Object.fromEntries(reglas[0].headers.map((h) => [h.key, h.value]));
}

describe("encabezados de seguridad", () => {
  it("evita el sniffing de tipo de contenido y el embebido en iframes", async () => {
    const h = await encabezados();

    expect(h["X-Content-Type-Options"]).toBe("nosniff");
    expect(h["X-Frame-Options"]).toBe("DENY");
  });

  it("limita el referrer al enviar a otros orígenes", async () => {
    const h = await encabezados();

    expect(h["Referrer-Policy"]).toBe("strict-origin-when-cross-origin");
  });

  it("permite solo el micrófono y bloquea la cámara y la geolocalización", async () => {
    const h = await encabezados();

    expect(h["Permissions-Policy"]).toBe("camera=(), geolocation=(), microphone=(self)");
  });
});
