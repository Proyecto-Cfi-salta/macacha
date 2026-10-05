from agent.rate_limit import LimitadorPorIP, ip_cliente


class _Reloj:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def test_permite_hasta_el_limite_y_rechaza_el_siguiente():
    reloj = _Reloj()
    lim = LimitadorPorIP(reloj)

    assert [lim.verificar("1.1.1.1", 3) for _ in range(3)] == [None, None, None]
    assert lim.verificar("1.1.1.1", 3) is not None


def test_el_rechazo_indica_cuantos_segundos_esperar():
    reloj = _Reloj()
    lim = LimitadorPorIP(reloj)
    lim.verificar("1.1.1.1", 1)
    reloj.t += 20

    espera = lim.verificar("1.1.1.1", 1)

    assert espera == 40


def test_la_espera_minima_es_un_segundo():
    reloj = _Reloj()
    lim = LimitadorPorIP(reloj)
    lim.verificar("1.1.1.1", 1)
    reloj.t += 59.9

    assert lim.verificar("1.1.1.1", 1) == 1


def test_despues_de_la_ventana_se_vuelve_a_permitir():
    reloj = _Reloj()
    lim = LimitadorPorIP(reloj)
    lim.verificar("1.1.1.1", 1)
    reloj.t += 60

    assert lim.verificar("1.1.1.1", 1) is None


def test_cada_ip_tiene_su_propio_contador():
    lim = LimitadorPorIP(_Reloj())
    lim.verificar("1.1.1.1", 1)

    assert lim.verificar("2.2.2.2", 1) is None


def test_un_intento_rechazado_no_se_cuenta_ni_estira_la_espera():
    reloj = _Reloj()
    lim = LimitadorPorIP(reloj)
    lim.verificar("1.1.1.1", 1)
    reloj.t += 30
    lim.verificar("1.1.1.1", 1)  # rechazado
    reloj.t += 30

    assert lim.verificar("1.1.1.1", 1) is None


def test_reiniciar_borra_el_estado():
    lim = LimitadorPorIP(_Reloj())
    lim.verificar("1.1.1.1", 1)
    lim.reiniciar()

    assert lim.verificar("1.1.1.1", 1) is None


def test_poda_las_ip_vencidas_para_no_crecer_sin_limite():
    reloj = _Reloj()
    lim = LimitadorPorIP(reloj)
    for i in range(1500):
        lim.verificar(f"10.0.{i // 250}.{i % 250}", 5)
    reloj.t += 120

    lim.verificar("9.9.9.9", 5)

    assert len(lim._eventos) < 10


def test_ip_cliente_usa_la_ultima_entrada_con_un_proxy():
    assert ip_cliente("203.0.113.5", "10.0.0.1", 1) == "203.0.113.5"


def test_ip_cliente_ignora_una_entrada_falsificada_a_la_izquierda():
    # el cliente mandó "1.2.3.4" y el proxy agregó la IP real al final
    assert ip_cliente("1.2.3.4, 203.0.113.5", "10.0.0.1", 1) == "203.0.113.5"


def test_ip_cliente_con_dos_proxies_toma_la_penultima():
    assert ip_cliente("falsa, 203.0.113.5, 10.0.0.9", "10.0.0.1", 2) == "203.0.113.5"


def test_ip_cliente_sin_encabezado_usa_el_host_directo():
    assert ip_cliente(None, "10.0.0.1", 1) == "10.0.0.1"
    assert ip_cliente("", "10.0.0.1", 1) == "10.0.0.1"


def test_ip_cliente_con_menos_entradas_que_proxies_no_es_confiable():
    assert ip_cliente("203.0.113.5", "10.0.0.1", 2) == "10.0.0.1"


def test_ip_cliente_sin_proxies_de_confianza_ignora_el_encabezado():
    assert ip_cliente("1.2.3.4", "10.0.0.1", 0) == "10.0.0.1"


def test_ip_cliente_sin_nada_devuelve_un_valor_estable():
    assert ip_cliente(None, None, 1) == "desconocida"
