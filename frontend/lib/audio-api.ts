import { BASE_URL } from "./api";
import { extensionPorMime } from "./audio-ui";

export type AudioTranscriptionResult = {
  text: string;
  provider: string;
  model: string;
  confidence: number | null;
  review_required: boolean;
  attempts: number;
  alternative_text: string;
  consensus_score: number | null;
  consensus_reason: string;
};

async function errorDetail(response: Response) {
  try {
    const body = await response.json();
    return String(body?.detail || "");
  } catch {
    return "";
  }
}

export async function transcribirAudio(
  blob: Blob,
  mimeType: string,
): Promise<AudioTranscriptionResult> {
  const contentType = mimeType || blob.type || "audio/webm";
  const extension = extensionPorMime(contentType);
  const url = `${BASE_URL}/audio/transcribe?filename=consulta.${extension}`;

  const response = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": contentType,
    },
    body: blob,
  });

  if (!response.ok) {
    const detail = await errorDetail(response);
    throw new Error(
      detail || "No pude transcribir el audio. Probá nuevamente.",
    );
  }

  const result = (await response.json()) as AudioTranscriptionResult;

  if (!result.text?.trim()) {
    throw new Error("La transcripción llegó vacía. Probá nuevamente.");
  }

  return result;
}
