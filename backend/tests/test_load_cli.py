import json

from ingest import load


class _FakeClient:
    def generate_embeddings(self, texts):
        return [[0.0] * 1536 for _ in texts]

    def generate_faqs(self, **kwargs):
        return [{"pregunta": "p", "respuesta": "r"}]


def test_main_prints_summary(tmp_path, monkeypatch, capsys):
    archivo = tmp_path / "sample.json"
    archivo.write_text(json.dumps([]), encoding="utf-8")

    monkeypatch.setattr(load, "get_connection", lambda: object())
    monkeypatch.setattr(load, "build_real_client", lambda: _FakeClient())
    monkeypatch.setattr(
        load,
        "ingest_file",
        lambda path, conn, embed_fn, faq_fn: {"nuevos": 0, "sin_cambios": 0, "nueva_version": 0},
    )

    load.main([str(archivo)])

    salida = capsys.readouterr().out
    assert "Trámites nuevos: 0" in salida
    assert "Trámites sin cambios: 0" in salida
    assert "Trámites con nueva versión: 0" in salida
