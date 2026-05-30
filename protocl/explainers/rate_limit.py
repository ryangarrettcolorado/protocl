"""v3.3 — per-user + per-app rate limiting and cost tracking (spec 2.7).

Per-user daily limits live in ``data/profiles/<profile_id>/llm_usage.json``:
- Tier 2: 50 generations/day (cached hits don't count)
- Tier 3: 10 questions/day

Per-app daily ceiling: 500 LLM calls total across all users. When exceeded,
Tier 2/3 are disabled (Tier 1 cached content stays available).

Token usage is logged to ``data/shared/llm_cost_log.csv``.
"""
from __future__ import annotations

from datetime import datetime, timezone

import storage
from storage import ProfileStorage


TIER2_DAILY_LIMIT = 50
TIER3_DAILY_LIMIT = 10
APP_DAILY_LIMIT = 500

USAGE_FILE = "llm_usage.json"
COST_FILE = "llm_cost_log.csv"
APP_USAGE_FILE = "app_llm_usage.json"

COST_COLUMNS = [
    "timestamp", "profile_id", "chart_id", "tier",
    "prompt_tokens", "completion_tokens", "model", "estimated_cost_usd",
]

# OpenAI pricing (USD per 1M tokens) — approximate, for the cost dashboard only.
_PRICING = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
}


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ── per-user usage ───────────────────────────────────────────────────────────

def _load_usage(store: ProfileStorage) -> dict:
    data = store.read_json(USAGE_FILE, default={}) or {}
    if data.get("date") != _today():
        return {"date": _today(), "tier2": 0, "tier3": 0}
    return data


def remaining(store: ProfileStorage, tier: int) -> int:
    usage = _load_usage(store)
    limit = TIER2_DAILY_LIMIT if tier == 2 else TIER3_DAILY_LIMIT
    used = usage.get(f"tier{tier}", 0)
    return max(0, limit - used)


def can_generate(store: ProfileStorage, tier: int) -> bool:
    if not app_budget_remaining() > 0:
        return False
    return remaining(store, tier) > 0


def record_generation(store: ProfileStorage, tier: int) -> None:
    """Count one *uncached* generation against the user + app budgets."""
    usage = _load_usage(store)
    usage[f"tier{tier}"] = usage.get(f"tier{tier}", 0) + 1
    try:
        store.write_json(USAGE_FILE, usage)
    except Exception:
        pass
    _increment_app()


# ── per-app ceiling ──────────────────────────────────────────────────────────

def _load_app() -> dict:
    path = storage.SHARED_DIR / APP_USAGE_FILE
    if not path.exists():
        return {"date": _today(), "count": 0}
    try:
        import json
        data = json.loads(path.read_text())
    except Exception:
        return {"date": _today(), "count": 0}
    if data.get("date") != _today():
        return {"date": _today(), "count": 0}
    return data


def _save_app(data: dict) -> None:
    import json
    storage.shared_path(APP_USAGE_FILE).write_text(json.dumps(data))


def app_budget_remaining() -> int:
    return max(0, APP_DAILY_LIMIT - _load_app().get("count", 0))


def _increment_app() -> None:
    data = _load_app()
    data["count"] = data.get("count", 0) + 1
    _save_app(data)


# ── cost logging ─────────────────────────────────────────────────────────────

def estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    in_rate, out_rate = _PRICING.get(model, (0.0, 0.0))
    return round(prompt_tokens / 1_000_000 * in_rate
                 + completion_tokens / 1_000_000 * out_rate, 6)


def log_cost(profile_id: str, chart_id: str, tier: int, model: str,
             prompt_tokens: int, completion_tokens: int) -> float:
    cost = estimate_cost(model, prompt_tokens, completion_tokens)
    storage.append_shared_csv(COST_FILE, {
        "timestamp": _now(),
        "profile_id": profile_id,
        "chart_id": chart_id,
        "tier": tier,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "model": model,
        "estimated_cost_usd": cost,
    }, COST_COLUMNS)
    return cost


def read_cost_log():
    return storage.read_shared_csv(COST_FILE, parse_dates=["timestamp"])
