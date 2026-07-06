import json


class OpenAIClient:
    EMBEDDING_MODEL = "text-embedding-3-small"
    FAQ_MODEL = "gpt-4o-mini"

    def __init__(self, sdk_client):
        self._sdk_client = sdk_client

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
        response = self._sdk_client.chat.completions.create(
            model=self.FAQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        )
        data = json.loads(response.choices[0].message.content)
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
        response = self._sdk_client.chat.completions.create(
            model=self.FAQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        )
        data = json.loads(response.choices[0].message.content)
        return data["orden"]


def build_real_client() -> OpenAIClient:
    from openai import OpenAI

    return OpenAIClient(OpenAI())
