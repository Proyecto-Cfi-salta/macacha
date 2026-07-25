from fastapi import HTTPException, Request

from agent.admin import security


def requiere_admin(request: Request) -> str:
    token = request.cookies.get("admin_session")
    if token is None:
        raise HTTPException(status_code=401, detail="No autenticado")

    admin_id = security.decodificar_token(token)
    if admin_id is None:
        raise HTTPException(status_code=401, detail="No autenticado")

    return admin_id
