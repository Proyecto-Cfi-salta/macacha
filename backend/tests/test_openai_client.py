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
    def __init__(self, content):
        self._content = content
        self.last_call = None

    def create(self, model, messages, response_format):
        self.last_call = {"model": model, "messages": messages, "response_format": response_format}
        return _FakeChatCompletionResponse(self._content)


class _FakeChat:
    def __init__(self, completions):
        self.completions = completions


class _FakeOpenAISDK:
    def __init__(self, vectors, faq_json_content):
        self.embeddings = _FakeEmbeddings(vectors)
        self.chat = _FakeChat(_FakeCompletions(faq_json_content))


def test_generate_embeddings_calls_api_and_returns_vectors():
    fake_sdk = _FakeOpenAISDK(vectors=[[0.1, 0.2], [0.3, 0.4]], faq_json_content="{}")
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
    fake_sdk = _FakeOpenAISDK(vectors=[], faq_json_content=faq_json)
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
