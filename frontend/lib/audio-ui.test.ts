import { describe, expect, it } from "vitest";
import {
  AVISO_PRIVACIDAD_AUDIO,
  extensionPorMime,
  formatearDuracion,
  textoAyudaAudio,
} from "./audio-ui";

describe("formatearDuracion", () => {
  it("formatea minutos y segundos con cero a la izquierda", () => {
    expect(formatearDuracion(0)).toBe("0:00");
    expect(formatearDuracion(7_000)).toBe("0:07");
    expect(formatearDuracion(65_000)).toBe("1:05");
    expect(formatearDuracion(600_000)).toBe("10:00");
  });

  it("trunca los milisegundos y no admite valores negativos", () => {
    expect(formatearDuracion(7_999)).toBe("0:07");
    expect(formatearDuracion(-500)).toBe("0:00");
  });
});

describe("extensionPorMime", () => {
  it("elige la extensión según el tipo de audio", () => {
    expect(extensionPorMime("audio/webm;codecs=opus")).toBe("webm");
    expect(extensionPorMime("audio/ogg;codecs=opus")).toBe("ogg");
    expect(extensionPorMime("audio/mp4")).toBe("mp4");
    expect(extensionPorMime("audio/x-m4a")).toBe("mp4");
    expect(extensionPorMime("audio/wav")).toBe("wav");
    expect(extensionPorMime("audio/mpeg")).toBe("mp3");
  });

  it("usa webm cuando no reconoce el tipo", () => {
    expect(extensionPorMime("")).toBe("webm");
    expect(extensionPorMime("application/octet-stream")).toBe("webm");
  });
});

const base = {
  microfono: "idle" as const,
  transcripcion: "idle" as const,
  duracionMs: 0,
  errorMicrofono: null,
  errorTranscripcion: null,
};

describe("textoAyudaAudio", () => {
  it("por defecto invita a escribir o grabar", () => {
    expect(textoAyudaAudio(base)).toBe("Podés escribir tu consulta o grabarla con el micrófono.");
  });

  it("mientras pide permiso lo dice y ya muestra el aviso de privacidad", () => {
    const t = textoAyudaAudio({ ...base, microfono: "requesting" });

    expect(t).toContain("Esperando permiso");
    expect(t).toContain(AVISO_PRIVACIDAD_AUDIO);
  });

  it("al grabar muestra la duración y el aviso de privacidad", () => {
    const t = textoAyudaAudio({ ...base, microfono: "recording", duracionMs: 7_000 });

    expect(t).toContain("Grabando 0:07");
    expect(t).toContain("Tocá detener");
    expect(t).toContain(AVISO_PRIVACIDAD_AUDIO);
  });

  it("el aviso de privacidad no afirma nada sobre la retención del proveedor", () => {
    expect(AVISO_PRIVACIDAD_AUDIO).toBe(
      "El audio se envía a un servicio externo para transcribirlo y no queda guardado en Macacha."
    );
  });

  it("indica cuando está transcribiendo", () => {
    expect(textoAyudaAudio({ ...base, transcripcion: "transcribing" })).toBe("Transcribiendo tu audio…");
  });

  it("pide revisar cuando la transcripción lo necesita", () => {
    expect(textoAyudaAudio({ ...base, transcripcion: "review" })).toContain("necesita revisión");
  });

  it("avisa que la transcripción está lista", () => {
    expect(textoAyudaAudio({ ...base, transcripcion: "ready" })).toContain("Transcripción lista");
  });

  it("muestra el error de transcripción", () => {
    expect(
      textoAyudaAudio({ ...base, transcripcion: "error", errorTranscripcion: "No pude transcribir." })
    ).toBe("No pude transcribir.");
  });

  it("muestra el error del micrófono", () => {
    expect(textoAyudaAudio({ ...base, microfono: "error", errorMicrofono: "Necesito permiso." })).toBe(
      "Necesito permiso."
    );
  });

  it("grabar tiene prioridad sobre un estado de transcripción viejo", () => {
    const t = textoAyudaAudio({ ...base, microfono: "recording", transcripcion: "review" });

    expect(t).toContain("Grabando");
  });
});
