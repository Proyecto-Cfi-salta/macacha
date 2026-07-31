import json
import os


class OpenAIClient:
    EMBEDDING_MODEL = "text-embedding-3-small"
    FAQ_MODEL_OPENAI = "gpt-4o-mini"
    FAQ_MODEL_GEMINI = "gemini-2.0-flash"

    def __init__(self, sdk_client, sdk_client_gemini=None):
        self._sdk_client = sdk_client
        self._sdk_client_gemini = sdk_client_gemini

    def generate_embeddings(self, texts: list[str]) -> list[list[float]]:
        response = self._sdk_client.embeddings.create(
            model=self.EMBEDDING_MODEL, input=texts
        )
        return [item.embedding for item in response.data]

    def generate_faqs(
        self,
        nombre_oficial: str,
        descripcion: str,
        requisitos: list[str],
        pasos: list[str],
    ) -> list[dict]:
        prompt = (
            "Generá entre 2 y 3 preguntas frecuentes con sus respuestas para el "
            "siguiente trámite de la administración pública de Salta.\n\n"
            f"Nombre: {nombre_oficial}\n"
            f"Descripción: {descripcion}\n"
            f"Requisitos: {'; '.join(requisitos)}\n"
            f"Pasos: {'; '.join(pasos)}\n\n"
            'Respondé únicamente con JSON con esta forma: '
            '{"faqs": [{"pregunta": "...", "respuesta": "..."}]}'
        )
        content = self._completar_con_fallback(prompt)
        data = json.loads(content)
        return data["faqs"]

    def rerank(self, query: str, candidatos: list[dict]) -> list[int]:
        candidatos_numerados = "\n".join(
            f"{i}. {candidato['texto']}" for i, candidato in enumerate(candidatos)
        )
        prompt = (
            "Ordená los siguientes fragmentos por relevancia real a la pregunta del "
            "usuario, del más relevante al menos relevante.\n\n"
            f"Pregunta: {query}\n\n"
            f"Fragmentos:\n{candidatos_numerados}\n\n"
            'Respondé únicamente con JSON con esta forma: '
            '{"orden": [<índices originales, del más al menos relevante>]}'
        )
        content = self._completar_con_fallback(prompt, temperature=0)
        data = json.loads(content)
        return data["orden"]

    def _completar_con_fallback(self, prompt: str, temperature: float | None = None) -> str:
        kwargs = {} if temperature is None else {"temperature": temperature}
        try:
            response = self._sdk_client.chat.completions.create(
                model=self.FAQ_MODEL_OPENAI,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                **kwargs,
            )
        except Exception:
            if self._sdk_client_gemini is None:
                raise
            print("OpenAI falló, usando fallback a Gemini")
            response = self._sdk_client_gemini.chat.completions.create(
                model=self.FAQ_MODEL_GEMINI,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                **kwargs,
            )
        return response.choices[0].message.content


def build_real_client() -> OpenAIClient:
    from openai import OpenAI

    sdk_client_gemini = None
    if os.environ.get("GEMINI_API_KEY"):
        sdk_client_gemini = OpenAI(
            api_key=os.environ["GEMINI_API_KEY"],
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        )
    return OpenAIClient(OpenAI(), sdk_client_gemini)
