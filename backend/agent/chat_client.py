import os


class ChatClient:
    MODEL_OPENAI = "gpt-4o-mini"
    MODEL_GEMINI = "gemini-2.0-flash"

    def __init__(self, sdk_client, sdk_client_gemini=None):
        self._sdk_client = sdk_client
        self._sdk_client_gemini = sdk_client_gemini

    def completar_streaming(self, messages: list[dict], tools: list[dict]):
        try:
            stream = self._sdk_client.chat.completions.create(
                model=self.MODEL_OPENAI, messages=messages, tools=tools, stream=True
            )
            proveedor = "openai"
        except Exception:
            if self._sdk_client_gemini is None:
                raise
            print("OpenAI falló, usando fallback a Gemini")
            stream = self._sdk_client_gemini.chat.completions.create(
                model=self.MODEL_GEMINI, messages=messages, tools=tools, stream=True
            )
            proveedor = "gemini"

        contenido_acumulado = ""
        tool_calls_acumulados: dict[int, dict] = {}

        for chunk in stream:
            delta = chunk.choices[0].delta
            if delta.content:
                contenido_acumulado += delta.content
                yield {"tipo": "delta", "texto": delta.content}
            if delta.tool_calls:
                for tc in delta.tool_calls:
                    entrada = tool_calls_acumulados.setdefault(
                        tc.index,
                        {"id": None, "type": "function", "function": {"name": "", "arguments": ""}},
                    )
                    if tc.id:
                        entrada["id"] = tc.id
                    if tc.function and tc.function.name:
                        entrada["function"]["name"] += tc.function.name
                    if tc.function and tc.function.arguments:
                        entrada["function"]["arguments"] += tc.function.arguments

        tool_calls = [tool_calls_acumulados[i] for i in sorted(tool_calls_acumulados)] or None

        yield {
            "tipo": "fin",
            "content": contenido_acumulado or None,
            "tool_calls": tool_calls,
            "proveedor": proveedor,
        }


def build_real_chat_client() -> ChatClient:
    from openai import OpenAI

    sdk_client_gemini = None
    if os.environ.get("GEMINI_API_KEY"):
        sdk_client_gemini = OpenAI(
            api_key=os.environ["GEMINI_API_KEY"],
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        )
    return ChatClient(OpenAI(), sdk_client_gemini)
