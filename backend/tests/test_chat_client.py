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
    def __init__(self, message):
        self._message = message
        self.last_call = None

    def create(self, model, messages, tools):
        self.last_call = {"model": model, "messages": messages, "tools": tools}
        return _FakeChatCompletionResponse(self._message)


class _FakeChat:
    def __init__(self, completions):
        self.completions = completions


class _FakeOpenAISDK:
    def __init__(self, message):
        self.chat = _FakeChat(_FakeCompletions(message))


def test_completar_devuelve_respuesta_sin_tool_calls():
    fake_sdk = _FakeOpenAISDK(_FakeMessage(content="Hola, ¿en qué te ayudo?"))
    client = ChatClient(fake_sdk)

    resultado = client.completar(messages=[{"role": "user", "content": "hola"}], tools=[])

    assert resultado == {"role": "assistant", "content": "Hola, ¿en qué te ayudo?", "tool_calls": None}
    assert fake_sdk.chat.completions.last_call["model"] == "gpt-4o-mini"


def test_completar_devuelve_tool_calls_normalizados():
    argumentos = json.dumps({"query": "acta"})
    tool_call = _FakeToolCall("call_1", "buscar_tramite", argumentos)
    fake_sdk = _FakeOpenAISDK(_FakeMessage(content=None, tool_calls=[tool_call]))
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
    }
