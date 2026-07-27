import os


class ChatClient:
    MODEL_OPENAI = "gpt-4o-mini"
    MODEL_GEMINI = "gemini-2.0-flash"

    def __init__(self, sdk_client, sdk_client_gemini=None):
        self._sdk_client = sdk_client
        self._sdk_client_gemini = sdk_client_gemini

    def completar(self, messages: list[dict], tools: list[dict]) -> dict:
        try:
            response = self._sdk_client.chat.completions.create(
                model=self.MODEL_OPENAI, messages=messages, tools=tools
            )
            proveedor = "openai"
        except Exception:
            if self._sdk_client_gemini is None:
                raise
            print("OpenAI falló, usando fallback a Gemini")
            response = self._sdk_client_gemini.chat.completions.create(
                model=self.MODEL_GEMINI, messages=messages, tools=tools
            )
            proveedor = "gemini"

        mensaje = response.choices[0].message

        tool_calls = None
        if mensaje.tool_calls:
            tool_calls = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in mensaje.tool_calls
            ]

        return {
            "role": "assistant",
            "content": mensaje.content,
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
