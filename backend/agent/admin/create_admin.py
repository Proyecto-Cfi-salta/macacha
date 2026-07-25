import sys
from getpass import getpass

from dotenv import load_dotenv

from agent.admin import security
from agent.admin.repository import crear_admin
from db.connection import get_connection


def main(argv: list[str], password_input=getpass) -> None:
    load_dotenv()
    if len(argv) != 1:
        print("Uso: python -m agent.admin.create_admin <email>")
        sys.exit(1)

    email = argv[0]
    password = password_input("Contraseña: ")
    password_hash = security.hash_password(password)

    conn = get_connection()
    crear_admin(conn, email, password_hash)
    conn.commit()

    print(f"Admin creado: {email}")


if __name__ == "__main__":
    main(sys.argv[1:])
