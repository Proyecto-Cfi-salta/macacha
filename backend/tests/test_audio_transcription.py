from types import SimpleNamespace

import pytest

from agent import audio_transcription as at


class _FakeOpenAI:
    """Cliente falso: responde según el modelo pedido; una excepción simula una falla."""

    respuestas: dict = {}
    llamadas: list = []

    def __init__(self, api_key=None):
        self.audio = SimpleNamespace(transcriptions=SimpleNamespace(create=self._create))

    def _create(self, model, file, language, response_format, temperature):
        type(self).llamadas.append({"model": model, "language": language, "temperature": temperature, "nombre": file.name})
        r = type(self).respuestas[model]
        if isinstance(r, Exception):
            raise r
        return SimpleNamespace(text=r)


@pytest.fixture
def fake(monkeypatch):
    _FakeOpenAI.respuestas = {}
    _FakeOpenAI.llamadas = []
    monkeypatch.setattr(at, "OpenAI", _FakeOpenAI)
    monkeypatch.setenv("OPENAI_API_KEY", "clave-de-test")
    monkeypatch.delenv("AUDIO_TRANSCRIPTION_MODEL", raising=False)
    monkeypatch.delenv("AUDIO_TRANSCRIPTION_SECONDARY_MODEL", raising=False)
    monkeypatch.delenv("AUDIO_TRANSCRIPTION_CONSENSUS_THRESHOLD", raising=False)
    return _FakeOpenAI


def _transcribir(**kwargs):
    return at.transcribe_audio_bytes_detailed(b"audio", filename="c.webm", content_type="audio/webm", **kwargs)


def test_audio_vacio_lanza_value_error():
    with pytest.raises(ValueError, match="empty_audio"):
        at.transcribe_audio_bytes_detailed(b"")


def test_sin_clave_de_openai_lanza_runtime_error(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="audio_transcription_not_configured"):
        at.transcribe_audio_bytes_detailed(b"audio")


def test_dos_modelos_que_coinciden_dan_consenso_sin_revision(fake):
    fake.respuestas = {
        "gpt-4o-transcribe": "Quiero sacar el pasaporte",
        "gpt-4o-mini-transcribe": "Quiero sacar el pasaporte.",
    }

    r = _transcribir()

    assert r.text == "Quiero sacar el pasaporte"
    assert r.model == "gpt-4o-transcribe"
    assert r.attempts == 2
    assert r.review_required is False
    assert r.consensus_reason == "consensus_ok"
    assert r.alternative_text == ""
    assert r.consensus_score == 1.0
    assert [c["model"] for c in fake.llamadas] == ["gpt-4o-transcribe", "gpt-4o-mini-transcribe"]
    assert all(c["language"] == "es" and c["temperature"] == 0 for c in fake.llamadas)


def test_poco_consenso_pide_revision_y_ofrece_la_otra_lectura(fake):
    fake.respuestas = {
        "gpt-4o-transcribe": "Registro civil de Salta",
        "gpt-4o-mini-transcribe": "Denuncia por trabajo informal",
    }

    r = _transcribir()

    assert r.review_required is True
    assert r.consensus_reason == "low_consensus"
    assert r.alternative_text == "Denuncia por trabajo informal"
    assert r.text == "Registro civil de Salta"


def test_intenciones_contradictorias_piden_revision(fake):
    fake.respuestas = {
        "gpt-4o-transcribe": "¿Cuánto cuesta el DNI?",
        "gpt-4o-mini-transcribe": "¿Dónde queda la oficina del DNI?",
    }

    r = _transcribir()

    assert r.review_required is True
    assert r.consensus_reason == "intent_conflict"


def test_repeticion_marcada_se_considera_sospechosa(fake):
    fake.respuestas = {
        "gpt-4o-transcribe": "gracias gracias gracias gracias gracias gracias",
        "gpt-4o-mini-transcribe": "gracias gracias gracias gracias gracias gracias",
    }

    r = _transcribir()

    assert r.review_required is True
    assert r.consensus_reason == "suspicious_transcription"


def test_descarta_la_frase_inventada_con_audio_vacio_y_queda_una_sola_lectura(fake):
    fake.respuestas = {
        "gpt-4o-transcribe": "Subtítulos realizados por la comunidad de Amara.org",
        "gpt-4o-mini-transcribe": "Necesito mi partida de nacimiento",
    }

    r = _transcribir()

    assert r.text == "Necesito mi partida de nacimiento"
    assert r.attempts == 1
    assert r.review_required is True
    assert r.consensus_reason == "single_transcription_only"


def test_descarta_un_texto_en_otro_idioma(fake):
    fake.respuestas = {
        "gpt-4o-transcribe": "hello what time is it",
        "gpt-4o-mini-transcribe": "Quiero hacer una denuncia",
    }

    r = _transcribir()

    assert r.text == "Quiero hacer una denuncia"
    assert r.attempts == 1


def test_si_un_modelo_falla_el_otro_igual_responde_para_revision(fake):
    fake.respuestas = {
        "gpt-4o-transcribe": RuntimeError("429 de OpenAI"),
        "gpt-4o-mini-transcribe": "Quiero sacar el DNI",
    }

    r = _transcribir()

    assert r.text == "Quiero sacar el DNI"
    assert r.model == "gpt-4o-mini-transcribe"
    assert r.review_required is True
    assert r.consensus_reason == "single_transcription_only"


def test_si_fallan_los_dos_modelos_lanza_runtime_error(fake):
    fake.respuestas = {
        "gpt-4o-transcribe": RuntimeError("401"),
        "gpt-4o-mini-transcribe": RuntimeError("401"),
    }

    with pytest.raises(RuntimeError, match="audio_transcription_failed"):
        _transcribir()


def test_si_ningun_modelo_devuelve_texto_utilizable_lanza_value_error(fake):
    fake.respuestas = {"gpt-4o-transcribe": "   ", "gpt-4o-mini-transcribe": "Amara.org"}

    with pytest.raises(ValueError, match="empty_or_invalid_transcription"):
        _transcribir()


def test_el_mismo_modelo_configurado_dos_veces_hace_una_sola_llamada(fake, monkeypatch):
    monkeypatch.setenv("AUDIO_TRANSCRIPTION_MODEL", "modelo-unico")
    monkeypatch.setenv("AUDIO_TRANSCRIPTION_SECONDARY_MODEL", "modelo-unico")
    fake.respuestas = {"modelo-unico": "Quiero sacar el DNI"}

    r = _transcribir()

    assert len(fake.llamadas) == 1
    assert r.attempts == 1
    assert r.consensus_reason == "single_transcription_only"


def test_los_modelos_y_el_umbral_se_configuran_por_entorno(fake, monkeypatch):
    monkeypatch.setenv("AUDIO_TRANSCRIPTION_MODEL", "principal-x")
    monkeypatch.setenv("AUDIO_TRANSCRIPTION_SECONDARY_MODEL", "secundario-y")
    monkeypatch.setenv("AUDIO_TRANSCRIPTION_CONSENSUS_THRESHOLD", "0.99")
    fake.respuestas = {"principal-x": "Quiero sacar el pasaporte", "secundario-y": "Quiero sacar el pasaporte hoy"}

    r = _transcribir()

    assert [c["model"] for c in fake.llamadas] == ["principal-x", "secundario-y"]
    assert r.consensus_reason == "low_consensus"


def test_el_nombre_de_archivo_se_sanea_y_recibe_extension(fake):
    fake.respuestas = {"gpt-4o-transcribe": "Quiero sacar el DNI", "gpt-4o-mini-transcribe": "Quiero sacar el DNI"}

    at.transcribe_audio_bytes_detailed(b"audio", filename="../../etc/passwd", content_type="audio/webm")

    nombre = fake.llamadas[0]["nombre"]
    assert "/" not in nombre and ".." not in nombre
    assert nombre.endswith(".webm")


def test_safe_audio_filename_conserva_extension_valida_y_completa_la_que_falta():
    assert at._safe_audio_filename("grabacion.mp3", None) == "grabacion.mp3"
    assert at._safe_audio_filename(None, "audio/ogg") == "consulta-audio.ogg"
    assert at._safe_audio_filename("sin extension", "audio/webm") == "sin-extension.webm"


def test_clean_transcription_quita_comillas_y_espacios_repetidos():
    assert at._clean_transcription('  "Quiero   sacar el DNI"  ') == "Quiero sacar el DNI"


def test_to_dict_expone_todos_los_campos(fake):
    fake.respuestas = {"gpt-4o-transcribe": "Quiero sacar el DNI", "gpt-4o-mini-transcribe": "Quiero sacar el DNI"}

    d = _transcribir().to_dict()

    assert set(d) == {
        "text", "provider", "model", "confidence", "review_required", "attempts",
        "alternative_text", "consensus_score", "consensus_reason",
    }
