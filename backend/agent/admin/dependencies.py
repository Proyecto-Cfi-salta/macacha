from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request

from agent.admin import security


@dataclass
class AdminActual:
    id: str
    rol: str
    organismo_id: int | None


def requiere_admin(request: Request) -> AdminActual:
    token = request.cookies.get("admin_session")
    if token is None:
        raise HTTPException(status_code=401, detail="No autenticado")

    payload = security.decodificar_token(token)
    if payload is None:
        raise HTTPException(status_code=401, detail="No autenticado")

    return AdminActual(id=payload["sub"], rol=payload["rol"], organismo_id=payload["organismo_id"])


def requiere_super_admin(admin: AdminActual = Depends(requiere_admin)) -> AdminActual:
    if admin.rol != "super_admin":
        raise HTTPException(status_code=403, detail="Requiere permisos de super admin")
    return admin
