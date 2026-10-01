import re

MAX_LONGITUD_EMAIL = 254
_PATRON_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalizar_email_contacto(valor: str | None) -> str | None:
    if valor is None:
        return None
    limpio = valor.strip()
    if not limpio:
        return None
    if len(limpio) > MAX_LONGITUD_EMAIL or not _PATRON_EMAIL.match(limpio):
        raise ValueError("Ingresá un email válido, por ejemplo mesa@organismo.gob.ar")
    return limpio
