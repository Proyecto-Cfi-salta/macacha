"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export type MicrophoneStatus =
  | "idle"
  | "requesting"
  | "recording"
  | "ready"
  | "error";

export type MicrophoneRecording = {
  blob: Blob;
  mimeType: string;
  durationMs: number;
};

const MIME_CANDIDATES = [
  "audio/webm;codecs=opus",
  "audio/webm",
  "audio/ogg;codecs=opus",
  "audio/mp4",
];

function pickMimeType() {
  if (typeof MediaRecorder === "undefined") return "";

  return (
    MIME_CANDIDATES.find((candidate) =>
      MediaRecorder.isTypeSupported(candidate),
    ) ?? ""
  );
}

function microphoneErrorMessage(error: unknown) {
  if (error instanceof DOMException) {
    if (error.name === "NotAllowedError" || error.name === "SecurityError") {
      return "Necesito permiso para usar el micrófono.";
    }

    if (error.name === "NotFoundError" || error.name === "DevicesNotFoundError") {
      return "No encontré un micrófono disponible.";
    }

    if (error.name === "NotReadableError" || error.name === "TrackStartError") {
      return "El micrófono está siendo usado por otra aplicación.";
    }
  }

  return "No pude iniciar el micrófono. Revisá los permisos del navegador.";
}

export function useMicrophoneRecorder() {
  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<BlobPart[]>([]);
  const cancelledRef = useRef(false);
  const failedRef = useRef(false);
  const startedAtRef = useRef<number | null>(null);

  const [status, setStatus] = useState<MicrophoneStatus>("idle");
  const [recording, setRecording] = useState<MicrophoneRecording | null>(null);
  const [elapsedMs, setElapsedMs] = useState(0);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const releaseStream = useCallback(() => {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
  }, []);

  const clearRecording = useCallback(() => {
    setRecording(null);
    setElapsedMs(0);
    setErrorMessage(null);
    setStatus("idle");
  }, []);

  const stopRecording = useCallback(() => {
    const recorder = recorderRef.current;

    if (recorder && recorder.state !== "inactive") {
      recorder.stop();
    }
  }, []);

  const cancelRecording = useCallback(() => {
    cancelledRef.current = true;
    setRecording(null);
    setElapsedMs(0);

    const recorder = recorderRef.current;

    if (recorder && recorder.state !== "inactive") {
      recorder.stop();
      return;
    }

    releaseStream();
    setStatus("idle");
  }, [releaseStream]);

  const startRecording = useCallback(async () => {
    if (
      typeof window === "undefined" ||
      !navigator.mediaDevices?.getUserMedia ||
      typeof MediaRecorder === "undefined"
    ) {
      setErrorMessage("Este navegador no admite grabación desde el micrófono.");
      setStatus("error");
      return;
    }

    try {
      setStatus("requesting");
      setErrorMessage(null);
      setRecording(null);
      setElapsedMs(0);
      chunksRef.current = [];
      cancelledRef.current = false;
      failedRef.current = false;

      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });

      streamRef.current = stream;

      const mimeType = pickMimeType();
      const recorder = mimeType
        ? new MediaRecorder(stream, { mimeType })
        : new MediaRecorder(stream);

      recorderRef.current = recorder;

      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          chunksRef.current.push(event.data);
        }
      };

      recorder.onerror = () => {
        failedRef.current = true;
        setErrorMessage("Se produjo un error mientras grababa el audio.");
        setStatus("error");
        releaseStream();
      };

      recorder.onstop = () => {
        const durationMs = startedAtRef.current
          ? Math.max(0, Date.now() - startedAtRef.current)
          : elapsedMs;

        startedAtRef.current = null;
        recorderRef.current = null;
        releaseStream();

        if (failedRef.current) {
          failedRef.current = false;
          chunksRef.current = [];
          setRecording(null);
          return;
        }

        if (cancelledRef.current) {
          cancelledRef.current = false;
          chunksRef.current = [];
          setRecording(null);
          setElapsedMs(0);
          setStatus("idle");
          return;
        }

        const finalMimeType = recorder.mimeType || mimeType || "audio/webm";
        const blob = new Blob(chunksRef.current, { type: finalMimeType });
        chunksRef.current = [];

        if (blob.size === 0) {
          setErrorMessage("No se registró audio. Probá nuevamente.");
          setStatus("error");
          return;
        }

        setRecording({ blob, mimeType: finalMimeType, durationMs });
        setElapsedMs(durationMs);
        setStatus("ready");
      };

      startedAtRef.current = Date.now();
      recorder.start(250);
      setStatus("recording");
    } catch (error) {
      releaseStream();
      setErrorMessage(microphoneErrorMessage(error));
      setStatus("error");
    }
  }, [releaseStream]);

  useEffect(() => {
    if (status !== "recording") return;

    const timer = window.setInterval(() => {
      if (startedAtRef.current) {
        setElapsedMs(Date.now() - startedAtRef.current);
      }
    }, 250);

    return () => window.clearInterval(timer);
  }, [status]);

  useEffect(() => {
    return () => {
      cancelledRef.current = true;

      if (recorderRef.current) {
        recorderRef.current.ondataavailable = null;
        recorderRef.current.onerror = null;
        recorderRef.current.onstop = null;

        if (recorderRef.current.state !== "inactive") {
          recorderRef.current.stop();
        }
      }

      releaseStream();
    };
  }, [releaseStream]);

  return {
    status,
    recording,
    elapsedMs,
    errorMessage,
    startRecording,
    stopRecording,
    cancelRecording,
    clearRecording,
  };
}
