import sys

from dotenv import load_dotenv

from db.connection import get_connection
from ingest.loader import ingest_file
from ingest.openai_client import build_real_client


def main(argv: list[str]) -> None:
    load_dotenv()
    if len(argv) != 1:
        print("Uso: python -m ingest.load <archivo.json>")
        sys.exit(1)

    path = argv[0]
    conn = get_connection()
    client = build_real_client()

    resumen = ingest_file(path, conn, client.generate_embeddings, client.generate_faqs)

    print(f"Trámites nuevos: {resumen['nuevos']}")
    print(f"Trámites sin cambios: {resumen['sin_cambios']}")
    print(f"Trámites con nueva versión: {resumen['nueva_version']}")


if __name__ == "__main__":
    main(sys.argv[1:])
