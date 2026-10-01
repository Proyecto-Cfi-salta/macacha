import pytest

from agent.admin.email_contacto import MAX_LONGITUD_EMAIL, normalizar_email_contacto


def test_none_devuelve_none():
    assert normalizar_email_contacto(None) is None


@pytest.mark.parametrize("valor", ["", "   ", "\n\t "])
def test_vacio_o_solo_espacios_devuelve_none_y_no_cadena_vacia(valor):
    assert normalizar_email_contacto(valor) is None


def test_recorta_los_espacios_alrededor():
    assert normalizar_email_contacto("  mesa@salta.gob.ar \n") == "mesa@salta.gob.ar"


@pytest.mark.parametrize("valor", ["mesa@salta.gob.ar", "a@b.co", "nombre.apellido+tag@dominio.com.ar"])
def test_acepta_emails_validos(valor):
    assert normalizar_email_contacto(valor) == valor


@pytest.mark.parametrize(
    "valor",
    ["sin-arroba", "a@b", "a b@c.com", "a@@b.com", "@x.com", "a@", "a@x .com", "dos@a.com tres@b.com"],
)
def test_rechaza_emails_con_forma_invalida(valor):
    with pytest.raises(ValueError):
        normalizar_email_contacto(valor)


def test_acepta_exactamente_el_largo_maximo():
    valor = "a" * (MAX_LONGITUD_EMAIL - len("@x.co")) + "@x.co"
    assert len(valor) == MAX_LONGITUD_EMAIL
    assert normalizar_email_contacto(valor) == valor


def test_rechaza_un_caracter_de_mas():
    valor = "a" * (MAX_LONGITUD_EMAIL - len("@x.co") + 1) + "@x.co"
    assert len(valor) == MAX_LONGITUD_EMAIL + 1
    with pytest.raises(ValueError):
        normalizar_email_contacto(valor)
