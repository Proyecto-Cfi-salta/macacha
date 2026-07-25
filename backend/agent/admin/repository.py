def crear_admin(conn, email: str, password_hash: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO admins (email, password_hash) VALUES (%s, %s)
            ON CONFLICT (email) DO UPDATE SET password_hash = EXCLUDED.password_hash
            """,
            (email, password_hash),
        )


def obtener_admin_por_email(conn, email: str) -> dict | None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, email, password_hash FROM admins WHERE email = %s", (email,)
        )
        row = cur.fetchone()
        if row is None:
            return None
        return {"id": str(row[0]), "email": row[1], "password_hash": row[2]}


def obtener_admin_por_id(conn, admin_id: str) -> dict | None:
    with conn.cursor() as cur:
        cur.execute("SELECT id, email FROM admins WHERE id = %s", (admin_id,))
        row = cur.fetchone()
        if row is None:
            return None
        return {"id": str(row[0]), "email": row[1]}
