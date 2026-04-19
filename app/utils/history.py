import json
import logging
from datetime import datetime, timezone
from typing import Optional

from app.utils.redis_client import get_redis

logger = logging.getLogger(__name__)

HISTORY_KEY = "redaction:history"
HISTORY_ENTRY_PREFIX = "redaction:entry:"

def save_history_entry(
    job_id: str,
    filename: str,
    duration_sec: float,
    entities: list[dict],
    status: str = "done",
) -> None:
    redis = get_redis()

    entity_types = sorted({e["type"] for e in entities})
    created_at = datetime.now(timezone.utc).isoformat()

    entry = {
        "job_id": job_id,
        "filename": filename,
        "created_at": created_at,
        "duration_sec": duration_sec,
        "total_redacted": len(entities),
        "entity_types": json.dumps(entity_types, ensure_ascii=False),
        "status": status,
    }

    key = f"{HISTORY_ENTRY_PREFIX}{job_id}"
    redis.hset(key, mapping={k: str(v) for k, v in entry.items()})

    redis.expire(key, 60 * 60 * 24 * 90)

    score = datetime.now(timezone.utc).timestamp()
    redis.zadd(HISTORY_KEY, {job_id: score})


def get_history_entry(job_id: str) -> Optional[dict]:
    redis = get_redis()
    raw = redis.hgetall(f"{HISTORY_ENTRY_PREFIX}{job_id}")
    if not raw:
        return None
    return _decode_entry(raw)


def get_history(
    page: int = 1,
    page_size: int = 20,
    entity_type_filter: Optional[str] = None,
) -> dict:
    page_size = min(page_size, 100)
    redis = get_redis()

    all_ids: list[bytes] = redis.zrevrange(HISTORY_KEY, 0, -1)

    entries = []
    for jid_bytes in all_ids:
        jid = jid_bytes.decode() if isinstance(jid_bytes, bytes) else jid_bytes
        raw = redis.hgetall(f"{HISTORY_ENTRY_PREFIX}{jid}")
        if not raw:
            continue
        entry = _decode_entry(raw)

        if entity_type_filter:
            if entity_type_filter.upper() not in entry["entity_types"]:
                continue

        entries.append(entry)

    total = len(entries)
    start = (page - 1) * page_size
    end = start + page_size
    page_entries = entries[start:end]

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": max(1, (total + page_size - 1) // page_size),
        "items": page_entries,
    }


def delete_history_entry(job_id: str) -> bool:
    redis = get_redis()
    deleted = redis.delete(f"{HISTORY_ENTRY_PREFIX}{job_id}")
    redis.zrem(HISTORY_KEY, job_id)
    return deleted > 0


def _decode_entry(raw: dict) -> dict:
    decoded = {
        (k.decode() if isinstance(k, bytes) else k): (
            v.decode() if isinstance(v, bytes) else v
        )
        for k, v in raw.items()
    }
    decoded["total_redacted"] = int(decoded.get("total_redacted", 0))
    decoded["duration_sec"] = float(decoded.get("duration_sec", 0.0))
    decoded["entity_types"] = json.loads(decoded.get("entity_types", "[]"))
    return decoded