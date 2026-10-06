import json

from ingest.openai_client import OpenAIClient


class _FakeEmbeddingItem:
    def __init__(self, embedding):
        self.embedding = embedding


class _FakeEmbeddingResponse:
    def __init__(self, vectors):
        self.data = [_FakeEmbeddingItem(v) for v in vectors]


class _FakeEmbeddings:
    def __init__(self, vectors):
        self._vectors = vectors
        self.last_call = None

    def create(self, model, input):
        self.last_call = {"model": model, "input": input}
        return _FakeEmbeddingResponse(self._vectors)


class _FakeMessage:
    def __init__(self, content):
        self.content = content


class _FakeChoice:
    def __init__(self, content):
        self.message = _FakeMessage(content)


class _FakeChatCompletionResponse:
    def __init__(self, content):
        self.choices = [_FakeChoice(content)]


class _FakeCompletions:
    def __init__(self, content=None, error=None):
        self._content = content
        self._error = error
        self.last_call = None

    def create(self, model, messages, response_format, temperature=None):
        self.last_call = {
            "model": model,
            "messages": messages,
            "response_format": response_format,
            "temperature": temperature,
        }
        if self._error is not None:
            raise self._error
        return _FakeChatCompletionResponse(self._content)


class _FakeChat:
    def __init__(self, completions):
        self.completions = completions


class _FakeOpenAISDK:
    def __init__(self, vectors=None, content=None, error=None):
        self.embeddings = _FakeEmbeddings(vectors or [])
        self.chat = _FakeChat(_FakeCompletions(content=content, error=error))


def test_generate_embeddings_calls_api_and_returns_vectors():
    fake_sdk = _FakeOpenAISDK(vectors=[[0.1, 0.2], [0.3, 0.4]], content="{}")
    client = OpenAIClient(fake_sdk)

    resultado = client.generate_embeddings(["texto 1", "texto 2"])

    assert resultado == [[0.1, 0.2], [0.3, 0.4]]
    assert fake_sdk.embeddings.last_call == {
        "model": "text-embedding-3-small",
        "input": ["texto 1", "texto 2"],
    }


def test_generate_faqs_parses_json_response():
    faq_json = json.dumps(
        {
            "faqs": [
                {"pregunta": "¿Cómo hago el trámite?", "respuesta": "Online."},
                {"pregunta": "¿Cuánto cuesta?", "respuesta": "$6000."},
            ]
        }
    )
    fake_sdk = _FakeOpenAISDK(content=faq_json)
    client = OpenAIClient(fake_sdk)

    resultado = client.generate_faqs(
        nombre_oficial="Actas Regulares",
        descripcion="Descripción de prueba",
        requisitos=["DNI"],
        pasos=["Paso 1"],
    )

    assert resultado == [
        {"pregunta": "¿Cómo hago el trámite?", "respuesta": "Online."},
        {"pregunta": "¿Cuánto cuesta?", "respuesta": "$6000."},
    ]
    assert fake_sdk.chat.completions.last_call["model"] == "gpt-4o-mini"


def test_rerank_parses_json_response_as_order():
    orden_json = json.dumps({"orden": [2, 0, 1]})
    fake_sdk = _FakeOpenAISDK(content=orden_json)
    client = OpenAIClient(fake_sdk)

    candidatos = [
        {"texto": "fragmento A"},
        {"texto": "fragmento B"},
        {"texto": "fragmento C"},
    ]

    resultado = client.rerank("una pregunta cualquiera", candidatos)

    assert resultado == [2, 0, 1]
    assert fake_sdk.chat.completions.last_call["model"] == "gpt-4o-mini"


def test_rerank_usa_temperature_cero_para_resultados_deterministicos():
    orden_json = json.dumps({"orden": [0]})
    fake_sdk = _FakeOpenAISDK(content=orden_json)
    client = OpenAIClient(fake_sdk)

    client.rerank("una pregunta cualquiera", [{"texto": "fragmento A"}])

    assert fake_sdk.chat.completions.last_call["temperature"] == 0


def test_generate_faqs_no_fuerza_temperature_cero():
    faq_json = json.dumps({"faqs": [{"pregunta": "p", "respuesta": "r"}]})
    fake_sdk = _FakeOpenAISDK(content=faq_json)
    client = OpenAIClient(fake_sdk)

    client.generate_faqs(
        nombre_oficial="Actas Regulares", descripcion="desc", requisitos=["DNI"], pasos=["Paso 1"]
    )

    assert fake_sdk.chat.completions.last_call["temperature"] is None


def test_generate_faqs_usa_gemini_si_openai_falla():
    faq_json = json.dumps({"faqs": [{"pregunta": "p", "respuesta": "r"}]})
    fake_openai = _FakeOpenAISDK(error=RuntimeError("401 de OpenAI"))
    fake_gemini = _FakeOpenAISDK(content=faq_json)
    client = OpenAIClient(fake_openai, fake_gemini)

    resultado = client.generate_faqs(
        nombre_oficial="Actas Regulares", descripcion="desc", requisitos=["DNI"], pasos=["Paso 1"]
    )

    assert resultado == [{"pregunta": "p", "respuesta": "r"}]
    assert fake_gemini.chat.completions.last_call["model"] == "gemini-2.0-flash"


def test_rerank_usa_gemini_si_openai_falla():
    orden_json = json.dumps({"orden": [1, 0]})
    fake_openai = _FakeOpenAISDK(error=RuntimeError("401 de OpenAI"))
    fake_gemini = _FakeOpenAISDK(content=orden_json)
    client = OpenAIClient(fake_openai, fake_gemini)

    resultado = client.rerank("query", [{"texto": "a"}, {"texto": "b"}])

    assert resultado == [1, 0]
    assert fake_gemini.chat.completions.last_call["model"] == "gemini-2.0-flash"


def test_rerank_sin_cliente_gemini_propaga_error_de_openai():
    fake_openai = _FakeOpenAISDK(error=ValueError("401 de OpenAI"))
    client = OpenAIClient(fake_openai)

    try:
        client.rerank("query", [{"texto": "a"}])
        assert False, "debería haber propagado la excepción"
    except ValueError as exc:
        assert str(exc) == "401 de OpenAI"


def _prompt_de_rerank(candidatos, query="una pregunta"):
    fake_sdk = _FakeOpenAISDK(content=json.dumps({"orden": list(range(len(candidatos)))}))
    OpenAIClient(fake_sdk).rerank(query, candidatos)
    return fake_sdk.chat.completions.last_call["messages"][0]["content"]


def test_rerank_muestra_el_nombre_y_el_organismo_de_cada_fragmento():
    prompt = _prompt_de_rerank(
        [
            {"texto": "Requisitos: DNI", "nombre_oficial": "Actas Regulares", "organismo": "Registro Civil"},
            {"texto": "Pasos: pedir turno", "nombre_oficial": "Pasaporte Regular", "organismo": "Registro Civil"},
        ]
    )

    assert "0. [Actas Regulares · Registro Civil] Requisitos: DNI" in prompt
    assert "1. [Pasaporte Regular · Registro Civil] Pasos: pedir turno" in prompt


def test_rerank_sin_nombre_ni_organismo_deja_solo_el_texto():
    prompt = _prompt_de_rerank([{"texto": "fragmento A"}])

    assert "0. fragmento A" in prompt
    assert "[" not in prompt.split("Fragmentos:")[1].split("Respondé")[0]


def test_rerank_pide_priorizar_el_tramite_cuya_finalidad_coincide():
    prompt = _prompt_de_rerank([{"texto": "a", "nombre_oficial": "X", "organismo": "Y"}])

    assert "finalidad coincide exactamente" in prompt
    assert "de otro organismo" in prompt
