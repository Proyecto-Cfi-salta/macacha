from __future__ import annotations

from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
from io import BytesIO
import os
import re
import unicodedata

from openai import OpenAI


_ALLOWED_EXTENSIONS = {
    ".flac",
    ".mp3",
    ".mp4",
    ".mpeg",
    ".mpga",
    ".m4a",
    ".ogg",
    ".wav",
    ".webm",
}

_MIME_TO_EXTENSION = {
    "audio/flac": ".flac",
    "audio/mpeg": ".mp3",
    "audio/mp3": ".mp3",
    "audio/mp4": ".mp4",
    "video/mp4": ".mp4",
    "audio/x-m4a": ".m4a",
    "audio/m4a": ".m4a",
    "audio/ogg": ".ogg",
    "application/ogg": ".ogg",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/webm": ".webm",
    "video/webm": ".webm",
    "application/octet-stream": ".webm",
}

_REJECT_MARKERS = (
    "consulta ciudadana breve hablada en espanol de argentina",
    "transcribir solamente lo que la persona dice",
    "conservar nombres de organismos localidades y tramites",
    "no agregar subtitulos comentarios ni instrucciones",
    "asistente virtual del gobierno de la provincia de salta",
    "subtitulos realizados por la comunidad de amara org",
    "subtitulos por la comunidad de amara org",
    "subtitles by the amara org community",
    "amara org",
    "gracias por ver el video",
    "gracias por mirar el video",
    "thanks for watching",
    "subscribe to the channel",
)

_STOPWORDS = {
    "a", "al", "de", "del", "el", "la", "las", "los", "un", "una",
    "y", "o", "en", "por", "para", "con", "sin", "me", "te", "se",
    "mi", "tu", "su", "que", "como", "donde", "cuando", "cual", "cuanto",
}

_INTENT_TERMS = {
    "cost": {
        "cuanto", "cuesta", "cuestan", "costo", "precio", "vale", "pagar", "pago",
    },
    "location": {
        "donde", "direccion", "queda", "ubicacion", "lugar", "sede", "oficina",
    },
    "requirements": {
        "requisito", "requisitos", "necesito", "documentacion", "documentos",
    },
    "hours": {
        "horario", "horarios", "hora", "atienden", "atencion",
    },
    "process": {
        "como", "tramito", "tramitar", "hacer", "sacar", "obtener", "solicitar",
    },
}

_COMMON_SPANISH = {
    "hola", "buen", "buenos", "buenas", "dia", "dias", "tarde", "tardes",
    "noche", "noches", "gracias", "si", "no", "quiero", "necesito", "puedo",
    "como", "donde", "cuando", "cual", "cuanto", "que", "quien", "para", "por",
    "con", "sin", "del", "de", "la", "las", "el", "los", "una", "un", "en",
    "es", "son", "tengo", "hacer", "sacar", "pedir", "consultar", "direccion",
    "domicilio", "ubicacion", "oficina", "sede", "delegacion", "horario",
    "telefono", "contacto", "correo", "registro", "civil", "defensa",
    "consumidor", "trabajo", "tramite", "denuncia", "reclamo", "acta", "dni",
    "pasaporte", "requisitos", "costo", "gratuito", "turno", "documentacion",
    "salta", "oran", "tartagal", "metan", "cerrillos", "cafayate", "guemes",
}

_FOREIGN_MARKERS = {
    "hello", "thanks", "what", "where", "when", "please", "office", "address",
    "bonjour", "merci", "ciao", "grazie", "obrigado", "hallo", "danke",
}


@dataclass(frozen=True)
class TranscriptionResult:
    text: str
    provider: str
    model: str
    confidence: float | None
    review_required: bool
    attempts: int
    alternative_text: str = ""
    consensus_score: float | None = None
    consensus_reason: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class _Candidate:
    text: str
    model: str


def _normalize(value: object) -> str:
    text = str(value or "").casefold().strip()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = re.sub(r"https?://", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _clean_transcription(value: object) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip().strip("\"'“”")
    if not text:
        return ""

    normalized = _normalize(text)
    if not normalized:
        return ""

    if any(marker in normalized for marker in _REJECT_MARKERS):
        return ""

    tokens = normalized.split()
    if any(token in _FOREIGN_MARKERS for token in tokens):
        spanish_hits = sum(token in _COMMON_SPANISH for token in tokens)
        if spanish_hits == 0:
            return ""

    return text


def _safe_audio_filename(filename: str | None, content_type: str | None) -> str:
    original = (filename or "consulta-audio").strip()
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", original).strip(".-")
    if not cleaned:
        cleaned = "consulta-audio"

    lower = cleaned.lower()
    if any(lower.endswith(ext) for ext in _ALLOWED_EXTENSIONS):
        return cleaned

    mime = (content_type or "").split(";", 1)[0].strip().lower()
    extension = _MIME_TO_EXTENSION.get(mime, ".webm")
    return f"{cleaned}{extension}"


def _extract_text(response: object) -> str:
    if response is None:
        return ""
    if isinstance(response, str):
        return response.strip()
    if isinstance(response, dict):
        return str(response.get("text") or "").strip()
    return str(getattr(response, "text", "") or "").strip()


def _transcribe_once(
    client: OpenAI,
    data: bytes,
    safe_name: str,
    model: str,
) -> str:
    stream = BytesIO(data)
    stream.name = safe_name

    response = client.audio.transcriptions.create(
        model=model,
        file=stream,
        language="es",
        response_format="json",
        temperature=0,
    )
    return _clean_transcription(_extract_text(response))


def _token_set(value: str) -> set[str]:
    return {
        token
        for token in _normalize(value).split()
        if token and token not in _STOPWORDS
    }


def _token_overlap(left: str, right: str) -> float:
    a = _token_set(left)
    b = _token_set(right)

    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0

    return len(a & b) / max(1, len(a | b))


def _consensus_score(left: str, right: str) -> float:
    left_norm = _normalize(left)
    right_norm = _normalize(right)

    sequence = SequenceMatcher(None, left_norm, right_norm).ratio()
    overlap = _token_overlap(left, right)

    return round((sequence * 0.62) + (overlap * 0.38), 4)


def _intent_signature(value: str) -> set[str]:
    tokens = set(_normalize(value).split())
    return {
        name
        for name, terms in _INTENT_TERMS.items()
        if tokens & terms
    }


def _intent_conflict(left: str, right: str) -> bool:
    a = _intent_signature(left)
    b = _intent_signature(right)

    if not a or not b:
        return False

    return a.isdisjoint(b)


def _looks_suspicious(value: str) -> bool:
    normalized = _normalize(value)
    if not normalized:
        return True

    if any(marker in normalized for marker in _REJECT_MARKERS):
        return True

    tokens = normalized.split()
    if len(tokens) == 1:
        token = tokens[0]
        return token not in _COMMON_SPANISH and len(token) < 3

    # Repeticiones muy marcadas suelen ser una señal de alucinación STT.
    if len(tokens) >= 6 and len(set(tokens)) <= 2:
        return True

    return False


def _candidate_models() -> list[str]:
    configured = (
        os.environ.get("AUDIO_TRANSCRIPTION_MODEL", "gpt-4o-transcribe").strip()
        or "gpt-4o-transcribe"
    )
    secondary = (
        os.environ.get(
            "AUDIO_TRANSCRIPTION_SECONDARY_MODEL",
            "gpt-4o-mini-transcribe",
        ).strip()
        or "gpt-4o-mini-transcribe"
    )

    models: list[str] = []
    for model in (configured, secondary):
        if model and model not in models:
            models.append(model)

    return models[:2]


def transcribe_audio_bytes_detailed(
    data: bytes,
    *,
    filename: str | None = None,
    content_type: str | None = None,
) -> TranscriptionResult:
    if not data:
        raise ValueError("empty_audio")

    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("audio_transcription_not_configured")

    safe_name = _safe_audio_filename(filename, content_type)
    client = OpenAI(api_key=api_key)

    candidates: list[_Candidate] = []
    last_error: Exception | None = None

    for model in _candidate_models():
        try:
            text = _transcribe_once(client, data, safe_name, model)
        except Exception as exc:
            last_error = exc
            continue

        if text:
            candidates.append(_Candidate(text=text, model=model))

    if not candidates:
        if last_error is not None:
            raise RuntimeError("audio_transcription_failed") from last_error
        raise ValueError("empty_or_invalid_transcription")

    if len(candidates) == 1:
        only = candidates[0]
        return TranscriptionResult(
            text=only.text,
            provider="openai_consensus",
            model=only.model,
            confidence=None,
            review_required=True,
            attempts=1,
            consensus_reason="single_transcription_only",
        )

    first, second = candidates[0], candidates[1]
    score = _consensus_score(first.text, second.text)
    threshold = float(
        os.environ.get("AUDIO_TRANSCRIPTION_CONSENSUS_THRESHOLD", "0.66")
    )
    intent_conflict = _intent_conflict(first.text, second.text)
    suspicious = _looks_suspicious(first.text) or _looks_suspicious(second.text)

    consensus_ok = (
        score >= threshold
        and not intent_conflict
        and not suspicious
    )

    if intent_conflict:
        reason = "intent_conflict"
    elif suspicious:
        reason = "suspicious_transcription"
    elif score < threshold:
        reason = "low_consensus"
    else:
        reason = "consensus_ok"

    # Se conserva como principal la lectura del modelo configurado.
    # Si hay diferencias, la segunda lectura se informa para revisión.
    return TranscriptionResult(
        text=first.text,
        provider="openai_consensus",
        model=first.model,
        confidence=None,
        review_required=not consensus_ok,
        attempts=2,
        alternative_text="" if consensus_ok else second.text,
        consensus_score=score,
        consensus_reason=reason,
    )
