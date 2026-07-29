from agent.chat_client import ChatClient


class _FakeDeltaFunction:
    def __init__(self, name=None, arguments=None):
        self.name = name
        self.arguments = arguments


class _FakeToolCallDelta:
    def __init__(self, index, id=None, function=None):
        self.index = index
        self.id = id
        self.function = function


class _FakeDelta:
    def __init__(self, content=None, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls


class _FakeChunkChoice:
    def __init__(self, delta):
        self.delta = delta


class _FakeChunk:
    def __init__(self, delta):
        self.choices = [_FakeChunkChoice(delta)]


class _FakeCompletions:
    def __init__(self, chunks=None, error=None):
        self._chunks = chunks if chunks is not None else []
        self._error = error
        self.last_call = None
        self.llamadas = 0

    def create(self, model, messages, tools, stream=False):
        self.llamadas += 1
        self.last_call = {"model": model, "messages": messages, "tools": tools, "stream": stream}
        if self._error is not None:
            raise self._error
        return iter(self._chunks)


class _FakeChat:
    def __init__(self, completions):
        self.completions = completions


class _FakeOpenAISDK:
    def __init__(self, chunks=None, error=None):
        self.chat = _FakeChat(_FakeCompletions(chunks=chunks, error=error))


def test_completar_streaming_devuelve_respuesta_sin_tool_calls():
    chunks = [
        _FakeChunk(_FakeDelta(content="Hola, ")),
        _FakeChunk(_FakeDelta(content="¿en qué te ayudo?")),
    ]
    fake_openai = _FakeOpenAISDK(chunks=chunks)
    client = ChatClient(fake_openai)

    eventos = list(client.completar_streaming(messages=[{"role": "user", "content": "hola"}], tools=[]))

    deltas = [e["texto"] for e in eventos if e["tipo"] == "delta"]
    assert deltas == ["Hola, ", "¿en qué te ayudo?"]
    assert eventos[-1] == {
        "tipo": "fin",
        "content": "Hola, ¿en qué te ayudo?",
        "tool_calls": None,
        "proveedor": "openai",
    }
    assert fake_openai.chat.completions.last_call["model"] == "gpt-4o-mini"
    assert fake_openai.chat.completions.last_call["stream"] is True


def test_completar_streaming_acumula_tool_calls_fragmentados():
    chunks = [
        _FakeChunk(_FakeDelta(tool_calls=[
            _FakeToolCallDelta(0, id="call_1", function=_FakeDeltaFunction(name="buscar_tramite", arguments=""))
        ])),
        _FakeChunk(_FakeDelta(tool_calls=[
            _FakeToolCallDelta(0, function=_FakeDeltaFunction(arguments='{"query"'))
        ])),
        _FakeChunk(_FakeDelta(tool_calls=[
            _FakeToolCallDelta(0, function=_FakeDeltaFunction(arguments=': "acta"}'))
        ])),
    ]
    fake_openai = _FakeOpenAISDK(chunks=chunks)
    client = ChatClient(fake_openai)

    eventos = list(client.completar_streaming(messages=[{"role": "user", "content": "quiero un acta"}], tools=[]))

    assert len(eventos) == 1
    assert eventos[-1] == {
        "tipo": "fin",
        "content": None,
        "tool_calls": [
            {
                "id": "call_1",
                "type": "function",
                "function": {"name": "buscar_tramite", "arguments": '{"query": "acta"}'},
            }
        ],
        "proveedor": "openai",
    }


def test_completar_streaming_usa_gemini_si_openai_falla():
    fake_openai = _FakeOpenAISDK(error=RuntimeError("401 de OpenAI"))
    fake_gemini = _FakeOpenAISDK(chunks=[_FakeChunk(_FakeDelta(content="Respuesta de Gemini"))])
    client = ChatClient(fake_openai, fake_gemini)

    eventos = list(client.completar_streaming(messages=[{"role": "user", "content": "hola"}], tools=[]))

    deltas = [e["texto"] for e in eventos if e["tipo"] == "delta"]
    assert "".join(deltas) == "Respuesta de Gemini"
    assert eventos[-1] == {
        "tipo": "fin",
        "content": "Respuesta de Gemini",
        "tool_calls": None,
        "proveedor": "gemini",
    }
    assert fake_gemini.chat.completions.last_call["model"] == "gemini-2.0-flash"


def test_completar_streaming_no_llama_a_gemini_si_openai_responde_bien():
    fake_openai = _FakeOpenAISDK(chunks=[_FakeChunk(_FakeDelta(content="Hola"))])
    fake_gemini = _FakeOpenAISDK(error=RuntimeError("no debería llamarse"))
    client = ChatClient(fake_openai, fake_gemini)

    eventos = list(client.completar_streaming(messages=[{"role": "user", "content": "hola"}], tools=[]))

    assert eventos[-1]["proveedor"] == "openai"
    assert fake_gemini.chat.completions.llamadas == 0


def test_completar_streaming_sin_cliente_gemini_propaga_error_de_openai():
    fake_openai = _FakeOpenAISDK(error=ValueError("401 de OpenAI"))
    client = ChatClient(fake_openai)

    try:
        list(client.completar_streaming(messages=[{"role": "user", "content": "hola"}], tools=[]))
        assert False, "debería haber propagado la excepción"
    except ValueError as exc:
        assert str(exc) == "401 de OpenAI"


def test_completar_streaming_con_ambos_proveedores_fallando_propaga_error_de_gemini():
    fake_openai = _FakeOpenAISDK(error=ValueError("falla de OpenAI"))
    fake_gemini = _FakeOpenAISDK(error=RuntimeError("falla de Gemini"))
    client = ChatClient(fake_openai, fake_gemini)

    try:
        list(client.completar_streaming(messages=[{"role": "user", "content": "hola"}], tools=[]))
        assert False, "debería haber propagado la excepción"
    except RuntimeError as exc:
        assert str(exc) == "falla de Gemini"


def test_completar_streaming_corte_a_mitad_de_stream_no_reintenta_con_gemini():
    def chunks_que_se_cortan():
        yield _FakeChunk(_FakeDelta(content="Hola"))
        raise RuntimeError("se cortó la conexión")

    fake_openai = _FakeOpenAISDK(chunks=chunks_que_se_cortan())
    fake_gemini = _FakeOpenAISDK(chunks=[_FakeChunk(_FakeDelta(content="no debería usarse"))])
    client = ChatClient(fake_openai, fake_gemini)

    generador = client.completar_streaming(messages=[{"role": "user", "content": "hola"}], tools=[])

    primer_evento = next(generador)
    assert primer_evento == {"tipo": "delta", "texto": "Hola"}

    try:
        next(generador)
        assert False, "debería haber propagado la excepción"
    except RuntimeError as exc:
        assert str(exc) == "se cortó la conexión"
    assert fake_gemini.chat.completions.llamadas == 0
