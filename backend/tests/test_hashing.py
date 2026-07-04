from ingest.hashing import compute_content_hash


def test_same_content_different_key_order_produces_same_hash():
    snapshot_a = {"id": "RC-0001", "costo": "$6000"}
    snapshot_b = {"costo": "$6000", "id": "RC-0001"}

    assert compute_content_hash(snapshot_a) == compute_content_hash(snapshot_b)


def test_different_content_produces_different_hash():
    snapshot_a = {"id": "RC-0001", "costo": "$6000"}
    snapshot_b = {"id": "RC-0001", "costo": "$7000"}

    assert compute_content_hash(snapshot_a) != compute_content_hash(snapshot_b)
