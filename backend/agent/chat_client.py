class ChatClient:
    MODEL = "gpt-4o-mini"

    def __init__(self, sdk_client):
        self._sdk_client = sdk_client

    def completar(self, messages: list[dict], tools: list[dict]) -> dict:
        response = self._sdk_client.chat.completions.create(
            model=self.MODEL,
            messages=messages,
            tools=tools,
        )
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

        return {"role": "assistant", "content": mensaje.content, "tool_calls": tool_calls}


def build_real_chat_client() -> ChatClient:
    from openai import OpenAI

    return ChatClient(OpenAI())
