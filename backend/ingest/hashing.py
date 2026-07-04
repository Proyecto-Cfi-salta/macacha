import hashlib
import json


def compute_content_hash(snapshot: dict) -> str:
    canonical = json.dumps(snapshot, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
