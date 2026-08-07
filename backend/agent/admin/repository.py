def crear_admin(
    conn,
    email: str,
    password_hash: str,
    rol: str = "admin_organismo",
    organismo_id: int | None = None,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO admins (email, password_hash, rol, organismo_id)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (email) DO UPDATE SET
                password_hash = EXCLUDED.password_hash,
                rol = EXCLUDED.rol,
                organismo_id = EXCLUDED.organismo_id
            """,
            (email, password_hash, rol, organismo_id),
        )


def obtener_admin_por_email(conn, email: str) -> dict | None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, email, password_hash, rol, organismo_id, activo FROM admins WHERE email = %s",
            (email,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return {
            "id": str(row[0]),
            "email": row[1],
            "password_hash": row[2],
            "rol": row[3],
            "organismo_id": row[4],
            "activo": row[5],
        }


def obtener_admin_por_id(conn, admin_id: str) -> dict | None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, email, rol, organismo_id, activo FROM admins WHERE id = %s", (admin_id,)
        )
        row = cur.fetchone()
        if row is None:
            return None
        return {
            "id": str(row[0]),
            "email": row[1],
            "rol": row[2],
            "organismo_id": row[3],
            "activo": row[4],
        }


def listar_admins(conn) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT a.id, a.email, a.rol, o.nombre, a.activo
            FROM admins a
            LEFT JOIN organismos o ON o.id = a.organismo_id
            ORDER BY a.email
            """
        )
        return [
            {"id": str(id_), "email": email, "rol": rol, "organismo": organismo, "activo": activo}
            for id_, email, rol, organismo, activo in cur.fetchall()
        ]


def editar_admin(
    conn,
    admin_id: str,
    rol: str,
    organismo_id: int | None,
    activo: bool,
    password_hash: str | None = None,
) -> None:
    with conn.cursor() as cur:
        if password_hash is not None:
            cur.execute(
                """
                UPDATE admins SET rol = %s, organismo_id = %s, activo = %s, password_hash = %s
                WHERE id = %s
                """,
                (rol, organismo_id, activo, password_hash, admin_id),
            )
        else:
            cur.execute(
                "UPDATE admins SET rol = %s, organismo_id = %s, activo = %s WHERE id = %s",
                (rol, organismo_id, activo, admin_id),
            )
