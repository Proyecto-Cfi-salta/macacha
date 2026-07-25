from agent.admin import create_admin


class _FakeConn:
    def commit(self):
        pass


def test_main_crea_admin_con_password_hasheada(monkeypatch, capsys):
    llamada = {}

    monkeypatch.setattr(create_admin, "get_connection", lambda: _FakeConn())
    monkeypatch.setattr(
        create_admin.security, "hash_password", lambda password: f"hash-de-{password}"
    )

    def _fake_crear_admin(conn, email, password_hash):
        llamada["email"] = email
        llamada["password_hash"] = password_hash

    monkeypatch.setattr(create_admin, "crear_admin", _fake_crear_admin)

    create_admin.main(["admin@macacha.gob.ar"], password_input=lambda prompt: "secreta123")

    assert llamada == {"email": "admin@macacha.gob.ar", "password_hash": "hash-de-secreta123"}
    assert "admin@macacha.gob.ar" in capsys.readouterr().out


def test_main_sin_email_imprime_uso_y_sale(capsys):
    try:
        create_admin.main([])
        assert False, "debería haber salido con sys.exit"
    except SystemExit as exc:
        assert exc.code == 1
    assert "Uso:" in capsys.readouterr().out
