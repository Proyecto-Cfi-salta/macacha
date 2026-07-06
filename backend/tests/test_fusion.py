from retrieval.fusion import fusionar_rrf


def test_fusiona_por_posicion_ordinal_no_por_score_absoluto():
    chunk_a = {"chunk_id": "a", "texto": "chunk a"}
    chunk_b = {"chunk_id": "b", "texto": "chunk b"}
    chunk_c = {"chunk_id": "c", "texto": "chunk c"}

    # "a" está 1° en vectorial y 3° en textual (aparece en ambos)
    # "b" está 2° solo en vectorial
    # "c" está 1° solo en textual
    ranking_vectorial = [chunk_a, chunk_b]
    ranking_textual = [chunk_c, {"chunk_id": "x", "texto": "otro"}, chunk_a]

    resultado = fusionar_rrf(ranking_vectorial, ranking_textual, k=60)

    # score(a) = 1/61 + 1/63 ≈ 0.032266 (aparece en ambos rankings)
    # score(c) = 1/61 ≈ 0.016393 (1° en textual)
    # score(b) = 1/62 ≈ 0.016129 (2° en vectorial)
    assert [c["chunk_id"] for c in resultado] == ["a", "c", "b", "x"]


def test_dedupe_por_chunk_id():
    chunk_a = {"chunk_id": "a", "texto": "chunk a"}

    resultado = fusionar_rrf([chunk_a], [chunk_a])

    assert len(resultado) == 1
    assert resultado[0]["chunk_id"] == "a"


def test_listas_vacias_devuelve_lista_vacia():
    assert fusionar_rrf([], []) == []
