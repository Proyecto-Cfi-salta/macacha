import asyncio
import logging
import os

import pytest
from fastapi.testclient import TestClient

from agent import api, audio_transcription


def _resultado(**kw):
    base = dict(
        text="Quiero sacar el pasaporte", provider="openai_consensus", model="gpt-4o-transcribe",
        confidence=None, review_required=False, attempts=2, alternative_text="",
        consensus_score=1.0, consensus_reason="consensus_ok",
    )
    base.update(kw)
    return audio_transcription.TranscriptionResult(**base)


@pytest.fixture(autouse=True)
def _limpio(monkeypatch):
    api._limitador_audio.reiniciar()
    for nombre in ("AUDIO_MAX_BYTES", "AUDIO_RATE_LIMIT_PER_MINUTE", "AUDIO_PROXY_HOPS"):
        monkeypatch.delenv(nombre, raising=False)
    yield
    api._limitador_audio.reiniciar()


@pytest.fixture
def transcribir(monkeypatch):
    """Reemplaza la transcripción real y registra cómo se la llamó."""
    llamadas = []

    def falso(data, *, filename=None, content_type=None):
        try:
            asyncio.get_running_loop()
            en_el_hilo_del_servidor = True
        except RuntimeError:
            en_el_hilo_del_servidor = False
        llamadas.append({"bytes": len(data), "filename": filename, "content_type": content_type,
                         "en_el_hilo_del_servidor": en_el_hilo_del_servidor})
        return _resultado()

    monkeypatch.setattr(audio_transcription, "transcribe_audio_bytes_detailed", falso)
    return llamadas


def _post(contenido=b"audio-de-prueba", tipo="audio/webm", **kw):
    headers = {"Content-Type": tipo} if tipo else {}
    headers.update(kw.pop("headers", {}))
    return TestClient(api.app).post("/audio/transcribe", content=contenido, headers=headers, **kw)


def test_audio_valido_devuelve_la_transcripcion(transcribir):
    r = _post()

    assert r.status_code == 200
    assert r.json()["text"] == "Quiero sacar el pasaporte"
    assert r.json()["review_required"] is False
    assert transcribir[0]["bytes"] == len(b"audio-de-prueba")
    assert transcribir[0]["content_type"] == "audio/webm"


def test_pasa_el_nombre_de_archivo_de_la_consulta(transcribir):
    _post(params={"filename": "consulta.webm"})

    assert transcribir[0]["filename"] == "consulta.webm"


def test_la_transcripcion_no_corre_en_el_hilo_del_servidor(transcribir):
    _post()

    assert transcribir[0]["en_el_hilo_del_servidor"] is False


def test_sin_content_type_se_trata_como_webm(transcribir):
    r = _post(tipo=None)

    assert r.status_code == 200
    assert transcribir[0]["content_type"] == "audio/webm"


@pytest.mark.parametrize("tipo", ["text/plain", "application/json", "image/png", "application/octet-stream"])
def test_formato_no_permitido_devuelve_415_sin_transcribir(transcribir, tipo):
    r = _post(tipo=tipo)

    assert r.status_code == 415
    assert transcribir == []


def test_content_type_con_parametros_se_acepta(transcribir):
    r = _post(tipo="audio/webm;codecs=opus")

    assert r.status_code == 200


def test_audio_vacio_devuelve_400(transcribir):
    r = _post(contenido=b"")

    assert r.status_code == 400
    assert transcribir == []


def test_content_length_mayor_al_maximo_devuelve_413_sin_transcribir(transcribir, monkeypatch):
    monkeypatch.setenv("AUDIO_MAX_BYTES", "10")

    r = _post(contenido=b"x" * 11)

    assert r.status_code == 413
    assert transcribir == []


def test_cuerpo_por_partes_sin_content_length_que_supera_el_maximo_devuelve_413(transcribir, monkeypatch):
    monkeypatch.setenv("AUDIO_MAX_BYTES", "10")

    def partes():
        for _ in range(100):
            yield b"x" * 4

    r = _post(contenido=partes())

    assert r.status_code == 413
    assert transcribir == []


def test_un_audio_justo_en_el_maximo_se_acepta(transcribir, monkeypatch):
    monkeypatch.setenv("AUDIO_MAX_BYTES", "10")

    r = _post(contenido=b"x" * 10)

    assert r.status_code == 200


def test_valor_invalido_de_audio_max_bytes_usa_el_defecto(transcribir, monkeypatch):
    monkeypatch.setenv("AUDIO_MAX_BYTES", "no-es-un-numero")

    r = _post(contenido=b"x" * 1000)

    assert r.status_code == 200


def test_el_limite_por_ip_devuelve_429_con_retry_after(transcribir, monkeypatch):
    monkeypatch.setenv("AUDIO_RATE_LIMIT_PER_MINUTE", "2")

    codigos = [_post().status_code for _ in range(3)]
    r = _post()

    assert codigos == [200, 200, 429]
    assert r.status_code == 429
    assert 1 <= int(r.headers["retry-after"]) <= 60
    assert "muchas consultas por voz" in r.json()["detail"]
    assert len(transcribir) == 2


def test_el_limite_se_aplica_antes_de_validar_el_formato(transcribir, monkeypatch):
    monkeypatch.setenv("AUDIO_RATE_LIMIT_PER_MINUTE", "1")
    _post()

    r = _post(tipo="text/plain")

    assert r.status_code == 429


def test_con_limite_cero_no_se_limita(transcribir, monkeypatch):
    monkeypatch.setenv("AUDIO_RATE_LIMIT_PER_MINUTE", "0")

    assert all(_post().status_code == 200 for _ in range(10))


def test_cada_ip_detras_del_proxy_tiene_su_propio_limite(transcribir, monkeypatch):
    monkeypatch.setenv("AUDIO_RATE_LIMIT_PER_MINUTE", "1")

    a = _post(headers={"X-Forwarded-For": "203.0.113.1"})
    b = _post(headers={"X-Forwarded-For": "203.0.113.2"})
    a2 = _post(headers={"X-Forwarded-For": "203.0.113.1"})

    assert (a.status_code, b.status_code, a2.status_code) == (200, 200, 429)


def test_una_entrada_falsificada_a_la_izquierda_no_evade_el_limite(transcribir, monkeypatch):
    monkeypatch.setenv("AUDIO_RATE_LIMIT_PER_MINUTE", "1")

    primero = _post(headers={"X-Forwarded-For": "1.1.1.1, 203.0.113.9"})
    segundo = _post(headers={"X-Forwarded-For": "2.2.2.2, 203.0.113.9"})

    assert primero.status_code == 200
    assert segundo.status_code == 429


def test_el_rechazo_por_limite_se_registra_con_la_ip_y_sin_contenido(transcribir, monkeypatch, caplog):
    monkeypatch.setenv("AUDIO_RATE_LIMIT_PER_MINUTE", "1")
    _post(headers={"X-Forwarded-For": "203.0.113.7"})

    with caplog.at_level(logging.WARNING, logger="agent.api"):
        _post(contenido=b"CONTENIDO-SECRETO", headers={"X-Forwarded-For": "203.0.113.7"})

    texto = " ".join(r.getMessage() for r in caplog.records)
    assert "203.0.113.7" in texto
    assert "CONTENIDO-SECRETO" not in texto


def test_sin_texto_confiable_devuelve_422(monkeypatch):
    def falso(data, **kw):
        raise ValueError("empty_or_invalid_transcription")

    monkeypatch.setattr(audio_transcription, "transcribe_audio_bytes_detailed", falso)

    r = _post()

    assert r.status_code == 422
    assert "transcripción confiable" in r.json()["detail"]


def test_sin_clave_de_openai_devuelve_503(monkeypatch):
    def falso(data, **kw):
        raise RuntimeError("audio_transcription_not_configured")

    monkeypatch.setattr(audio_transcription, "transcribe_audio_bytes_detailed", falso)

    r = _post()

    assert r.status_code == 503
    assert "no está configurada" in r.json()["detail"]


@pytest.mark.parametrize("error", [RuntimeError("audio_transcription_failed"), KeyError("inesperado")])
def test_falla_del_proveedor_o_error_inesperado_devuelve_502(monkeypatch, error):
    def falso(data, **kw):
        raise error

    monkeypatch.setattr(audio_transcription, "transcribe_audio_bytes_detailed", falso)

    r = _post()

    assert r.status_code == 502
    assert "inesperado" not in r.json()["detail"]


def test_el_audio_no_se_escribe_a_disco(transcribir, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    _post()

    assert list(tmp_path.iterdir()) == []


def test_cors_permite_el_preflight_del_audio_desde_el_frontend():
    origen = os.environ.get("FRONTEND_ORIGIN", "http://localhost:3000")

    r = TestClient(api.app).options(
        "/audio/transcribe",
        headers={
            "Origin": origen,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == origen
