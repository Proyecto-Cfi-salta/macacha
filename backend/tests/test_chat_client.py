import json

from agent.chat_client import ChatClient


class _FakeFunction:
    def __init__(self, name, arguments):
        self.name = name
        self.arguments = arguments


class _FakeToolCall:
    def __init__(self, id_, name, arguments):
        self.id = id_
        self.function = _FakeFunction(name, arguments)


class _FakeMessage:
    def __init__(self, content, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls


class _FakeChoice:
    def __init__(self, message):
        self.message = message


class _FakeChatCompletionResponse:
    def __init__(self, message):
        self.choices = [_FakeChoice(message)]


class _FakeCompletions:
    def __init__(self, message=None, error=None):
        self._message = message
        self._error = error
        self.last_call = None
        self.llamadas = 0

    def create(self, model, messages, tools):
        self.llamadas += 1
        self.last_call = {"model": model, "messages": messages, "tools": tools}
        if self._error is not None:
            raise self._error
        return _FakeChatCompletionResponse(self._message)


class _FakeChat:
    def __init__(self, completions):
        self.completions = completions


class _FakeOpenAISDK:
    def __init__(self, message=None, error=None):
        self.chat = _FakeChat(_FakeCompletions(message=message, error=error))


def test_completar_devuelve_respuesta_sin_tool_calls():
    fake_sdk = _FakeOpenAISDK(message=_FakeMessage(content="Hola, ¿en qué te ayudo?"))
    client = ChatClient(fake_sdk)

    resultado = client.completar(messages=[{"role": "user", "content": "hola"}], tools=[])

    assert resultado == {
        "role": "assistant",
        "content": "Hola, ¿en qué te ayudo?",
        "tool_calls": None,
        "proveedor": "openai",
    }
    assert fake_sdk.chat.completions.last_call["model"] == "gpt-4o-mini"


def test_completar_devuelve_tool_calls_normalizados():
    argumentos = json.dumps({"query": "acta"})
    tool_call = _FakeToolCall("call_1", "buscar_tramite", argumentos)
    fake_sdk = _FakeOpenAISDK(message=_FakeMessage(content=None, tool_calls=[tool_call]))
    client = ChatClient(fake_sdk)

    resultado = client.completar(messages=[{"role": "user", "content": "quiero un acta"}], tools=[])

    assert resultado == {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "call_1",
                "type": "function",
                "function": {"name": "buscar_tramite", "arguments": argumentos},
            }
        ],
        "proveedor": "openai",
    }


def test_completar_usa_gemini_si_openai_falla():
    fake_openai = _FakeOpenAISDK(error=RuntimeError("401 de OpenAI"))
    fake_gemini = _FakeOpenAISDK(message=_FakeMessage(content="Respuesta de Gemini"))
    client = ChatClient(fake_openai, fake_gemini)

    resultado = client.completar(messages=[{"role": "user", "content": "hola"}], tools=[])

    assert resultado == {
        "role": "assistant",
        "content": "Respuesta de Gemini",
        "tool_calls": None,
        "proveedor": "gemini",
    }
    assert fake_gemini.chat.completions.last_call["model"] == "gemini-2.0-flash"


def test_completar_no_llama_a_gemini_si_openai_responde_bien():
    fake_openai = _FakeOpenAISDK(message=_FakeMessage(content="Hola"))
    fake_gemini = _FakeOpenAISDK(error=RuntimeError("no debería llamarse"))
    client = ChatClient(fake_openai, fake_gemini)

    resultado = client.completar(messages=[{"role": "user", "content": "hola"}], tools=[])

    assert resultado["proveedor"] == "openai"
    assert fake_gemini.chat.completions.llamadas == 0


def test_completar_sin_cliente_gemini_propaga_error_de_openai():
    fake_openai = _FakeOpenAISDK(error=ValueError("401 de OpenAI"))
    client = ChatClient(fake_openai)

    try:
        client.completar(messages=[{"role": "user", "content": "hola"}], tools=[])
        assert False, "debería haber propagado la excepción"
    except ValueError as exc:
        assert str(exc) == "401 de OpenAI"


def test_completar_con_ambos_proveedores_fallando_propaga_error_de_gemini():
    fake_openai = _FakeOpenAISDK(error=ValueError("falla de OpenAI"))
    fake_gemini = _FakeOpenAISDK(error=RuntimeError("falla de Gemini"))
    client = ChatClient(fake_openai, fake_gemini)

    try:
        client.completar(messages=[{"role": "user", "content": "hola"}], tools=[])
        assert False, "debería haber propagado la excepción"
    except RuntimeError as exc:
        assert str(exc) == "falla de Gemini"
