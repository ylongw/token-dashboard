#!/usr/bin/env python3
"""Aggregate OpenClaw session logs into daily usage data for the token dashboard."""

import json
import glob
import os
import sys
from datetime import datetime, timezone, timedelta
from collections import defaultdict
from pathlib import Path

# Asia/Shanghai = UTC+8
CST = timezone(timedelta(hours=8))

SESSION_DIR = os.path.expanduser("~/.openclaw/agents/main/sessions")
CLAUDE_CODE_DIR = os.path.expanduser("~/.claude/projects")
OUTPUT_DIR = Path.home() / ".token-dashboard" / "data"

# Models to skip (zero-token entries)
SKIP_MODELS = {"delivery-mirror", "gateway-injected"}

# Pricing table: $ per million tokens
# Used as fallback when provider-reported cost is zero/missing (e.g. Gemini CLI)
PRICING = {
    # Claude Opus 4.6 — https://docs.anthropic.com/en/docs/about-claude/pricing
    "Claude Opus 4.6":   {"input": 5.00,  "output": 25.00, "cacheRead": 0.50,  "cacheWrite": 6.25},
    # Claude Sonnet 4.6
    "Claude Sonnet 4.6": {"input": 3.00,  "output": 15.00, "cacheRead": 0.30,  "cacheWrite": 3.75},
    # Claude Sonnet 4.5
    "Claude Sonnet 4.5": {"input": 3.00,  "output": 15.00, "cacheRead": 0.30,  "cacheWrite": 3.75},
    # GPT-5.3 Codex — https://platform.openai.com/docs/pricing
    "GPT-5.3 Codex":     {"input": 1.75,  "output": 14.00, "cacheRead": 0.175, "cacheWrite": 0},
    # Gemini 3 Pro Preview — https://ai.google.dev/gemini-api/docs/pricing (≤200K context)
    "Gemini 3 Pro":      {"input": 2.00,  "output": 12.00, "cacheRead": 0.50,  "cacheWrite": 1.00},
    # Gemini 3 Flash Preview
    "Gemini 3 Flash":    {"input": 0.30,  "output": 2.50,  "cacheRead": 0.075, "cacheWrite": 0.15},
}


def normalize_model(model_id: str) -> str | None:
    """Normalize model ID to a display name with version suffix. Returns None for models to skip."""
    m = model_id.lower()
    # Strip provider prefix (e.g. "anthropic/", "openai/", "google-gemini-cli/")
    if "/" in m:
        m = m.split("/")[-1]

    if any(skip in m for skip in SKIP_MODELS):
        return None
    # Embedding models → skip
    if "embedding" in m or "gguf" in m:
        return None
    if m == "default":
        return None

    # Specific model matching (most specific first)
    if "gpt-5.3-codex" in m or "codex" in m:
        return "GPT-5.3 Codex"

    if "opus-4-6" in m or m == "opus":
        return "Claude Opus 4.6"
    if "opus-4-5" in m:
        return "Claude Opus 4.5"
    if "opus-4-1" in m:
        return "Claude Opus 4.1"
    if "opus" in m:
        return "Claude Opus 4.6"  # default opus

    if "sonnet-4-6" in m or m == "sonnet":
        return "Claude Sonnet 4.6"
    if "sonnet-4-5" in m:
        return "Claude Sonnet 4.5"
    if "sonnet-4" in m:
        return "Claude Sonnet 4"
    if "sonnet" in m:
        return "Claude Sonnet 4.6"  # default sonnet

    if "gemini-3-flash" in m:
        return "Gemini 3 Flash"
    if "gemini-3-pro" in m or "gemini-3" in m:
        return "Gemini 3 Pro"
    if "gemini" in m:
        return "Gemini"

    if "claude" in m:
        return "Claude"
    if "gpt" in m:
        return "GPT"

    return "Other"


def compute_cost(model_name: str, input_tokens: int, output_tokens: int,
                 cache_read: int, cache_write: int, reported_cost: float) -> float:
    """Return the best cost estimate. Use provider-reported cost if > 0, else calculate from pricing table."""
    if reported_cost > 0:
        return reported_cost
    pricing = PRICING.get(model_name)
    if not pricing:
        return 0.0
    cost = (
        input_tokens * pricing["input"] / 1_000_000
        + output_tokens * pricing["output"] / 1_000_000
        + cache_read * pricing["cacheRead"] / 1_000_000
        + cache_write * pricing["cacheWrite"] / 1_000_000
    )
    return cost


def parse_timestamp(ts) -> datetime | None:
    """Parse timestamp (ISO string or epoch ms) into a CST datetime."""
    if ts is None:
        return None
    if isinstance(ts, (int, float)):
        return datetime.fromtimestamp(ts / 1000, tz=CST)
    if isinstance(ts, str):
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            return dt.astimezone(CST)
        except ValueError:
            return None
    return None


def extract_usage(line_data: dict) -> dict | None:
    """Extract usage info from a JSONL line. Returns dict with model, usage, timestamp or None."""
    # Only process message-type lines
    if line_data.get("type") != "message":
        return None

    msg = line_data.get("message", {})

    # Only assistant messages have usage
    if msg.get("role") != "assistant":
        return None

    # Usage can be in message or top-level
    usage = msg.get("usage") or line_data.get("usage")
    if not usage:
        return None

    model = msg.get("model") or line_data.get("model")
    if not model:
        return None

    normalized = normalize_model(model)
    if normalized is None:
        return None

    # Get timestamp
    ts = msg.get("timestamp") or line_data.get("timestamp")
    dt = parse_timestamp(ts)
    if dt is None:
        return None

    input_tokens = usage.get("input", 0)
    output_tokens = usage.get("output", 0)
    cache_read = usage.get("cacheRead", 0)
    cache_write = usage.get("cacheWrite", 0)
    total_tokens = usage.get("totalTokens", 0) or (input_tokens + output_tokens + cache_read + cache_write)

    cost_data = usage.get("cost", {})
    reported_cost = cost_data.get("total", 0) if isinstance(cost_data, dict) else 0
    total_cost = compute_cost(normalized, input_tokens, output_tokens, cache_read, cache_write, reported_cost)

    slot = dt.hour * 2 + dt.minute // 30  # 0-47

    return {
        "model": normalized,
        "date": dt.strftime("%Y-%m-%d"),
        "slot": slot,
        "input": input_tokens,
        "output": output_tokens,
        "cacheRead": cache_read,
        "cacheWrite": cache_write,
        "totalTokens": total_tokens,
        "cost": total_cost,
    }


def extract_claude_code_usage(line_data: dict) -> dict | None:
    """Extract usage from a Claude Code JSONL line (Anthropic native format)."""
    msg = line_data.get("message", {})

    # Only assistant messages with usage
    if msg.get("role") != "assistant":
        return None

    usage = msg.get("usage")
    if not usage:
        return None

    model = msg.get("model")
    if not model:
        return None

    normalized = normalize_model(model)
    if normalized is None:
        return None

    # Timestamp can be top-level or nested
    ts = line_data.get("timestamp") or msg.get("timestamp")
    dt = parse_timestamp(ts)
    if dt is None:
        return None

    # Anthropic native format: input_tokens, output_tokens,
    # cache_creation_input_tokens, cache_read_input_tokens
    input_tokens = usage.get("input_tokens", 0)
    output_tokens = usage.get("output_tokens", 0)
    cache_read = usage.get("cache_read_input_tokens", 0)
    cache_write = usage.get("cache_creation_input_tokens", 0)
    total_tokens = input_tokens + output_tokens + cache_read + cache_write

    # Claude Code doesn't report cost, always calculate
    total_cost = compute_cost(normalized, input_tokens, output_tokens, cache_read, cache_write, 0)

    slot = dt.hour * 2 + dt.minute // 30  # 0-47

    return {
        "model": normalized,
        "date": dt.strftime("%Y-%m-%d"),
        "slot": slot,
        "input": input_tokens,
        "output": output_tokens,
        "cacheRead": cache_read,
        "cacheWrite": cache_write,
        "totalTokens": total_tokens,
        "cost": total_cost,
    }


def aggregate():
    """Scan all session files and aggregate usage data."""
    files = glob.glob(os.path.join(SESSION_DIR, "*.jsonl"))
    print(f"Found {len(files)} session files")

    # day -> model -> aggregated stats
    daily = defaultdict(lambda: defaultdict(lambda: {
        "input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0,
        "totalTokens": 0, "cost": 0.0, "calls": 0,
    }))

    # intraday: date -> slot_index (0-47, 30min each) -> model -> totalTokens
    intraday = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))

    total_lines = 0
    usage_lines = 0
    errors = 0

    for filepath in files:
        try:
            with open(filepath, "r") as f:
                for line in f:
                    total_lines += 1
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        errors += 1
                        continue

                    result = extract_usage(data)
                    if result is None:
                        continue

                    usage_lines += 1
                    day = result["date"]
                    model = result["model"]
                    bucket = daily[day][model]
                    bucket["input"] += result["input"]
                    bucket["output"] += result["output"]
                    bucket["cacheRead"] += result["cacheRead"]
                    bucket["cacheWrite"] += result["cacheWrite"]
                    bucket["totalTokens"] += result["totalTokens"]
                    bucket["cost"] += result["cost"]
                    bucket["calls"] += 1
                    # Intraday: store slot index (0-47) for this entry
                    if result.get("slot") is not None:
                        intraday[day][result["slot"]][model] += result["totalTokens"]
        except Exception as e:
            errors += 1
            print(f"Error reading {filepath}: {e}", file=sys.stderr)

    print(f"[OpenClaw] Processed {total_lines} lines, {usage_lines} usage entries, {errors} errors")

    # --- Phase 2: Scan Claude Code session logs ---
    # Claude Code logs contain streaming chunks: multiple JSONL entries per API call
    # with the same msg_id but incrementing output_tokens.
    # We must deduplicate by msg_id, keeping only the final (highest output) entry.
    cc_files = glob.glob(os.path.join(CLAUDE_CODE_DIR, "**", "*.jsonl"), recursive=True)
    cc_total = 0
    cc_raw_usage = 0
    cc_errors = 0

    # First pass: collect all entries, keyed by msg_id
    # msg_id -> best entry (highest output_tokens)
    cc_by_msgid = {}

    for filepath in cc_files:
        try:
            with open(filepath, "r") as f:
                for line in f:
                    cc_total += 1
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        cc_errors += 1
                        continue

                    msg = data.get("message", {})
                    if msg.get("role") != "assistant":
                        continue
                    usage = msg.get("usage")
                    if not usage:
                        continue

                    cc_raw_usage += 1
                    msg_id = msg.get("id", "")
                    out_tokens = usage.get("output_tokens", 0)

                    if msg_id:
                        prev = cc_by_msgid.get(msg_id)
                        if prev is None or out_tokens > prev.get("message", {}).get("usage", {}).get("output_tokens", 0):
                            cc_by_msgid[msg_id] = data
                    else:
                        # No msg_id — use a unique key to avoid dedup
                        cc_by_msgid[f"_noid_{cc_raw_usage}"] = data
        except Exception as e:
            cc_errors += 1
            print(f"Error reading {filepath}: {e}", file=sys.stderr)

    # Second pass: process deduplicated entries
    cc_deduped = 0
    for data in cc_by_msgid.values():
        result = extract_claude_code_usage(data)
        if result is None:
            continue

        cc_deduped += 1
        day = result["date"]
        model = result["model"]
        bucket = daily[day][model]
        bucket["input"] += result["input"]
        bucket["output"] += result["output"]
        bucket["cacheRead"] += result["cacheRead"]
        bucket["cacheWrite"] += result["cacheWrite"]
        bucket["totalTokens"] += result["totalTokens"]
        bucket["cost"] += result["cost"]
        bucket["calls"] += 1
        if result.get("slot") is not None:
            intraday[day][result["slot"]][model] += result["totalTokens"]

    print(f"[Claude Code] Processed {cc_total} lines, {cc_raw_usage} raw → {cc_deduped} deduped usage entries from {len(cc_files)} files, {cc_errors} errors")

    return daily, intraday


def build_output(daily: dict, intraday: dict) -> dict:
    """Build the final JSON output structure."""
    now = datetime.now(CST)
    today = now.strftime("%Y-%m-%d")

    # Sort dates
    all_dates = sorted(daily.keys())

    # Build daily_by_model: [{date, model, ...}]
    daily_by_model = []
    for date in all_dates:
        for model, stats in sorted(daily[date].items()):
            daily_by_model.append({
                "date": date,
                "model": model,
                **stats,
                "cost": round(stats["cost"], 6),
            })

    # Per-model totals
    model_totals = defaultdict(lambda: {
        "input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0,
        "totalTokens": 0, "cost": 0.0, "calls": 0,
    })
    for entry in daily_by_model:
        m = model_totals[entry["model"]]
        for k in ("input", "output", "cacheRead", "cacheWrite", "totalTokens", "calls"):
            m[k] += entry[k]
        m["cost"] += entry["cost"]

    model_totals_list = []
    for model, stats in sorted(model_totals.items(), key=lambda x: -x[1]["totalTokens"]):
        model_totals_list.append({"model": model, **stats, "cost": round(stats["cost"], 6)})

    # Daily cost trend (all dates)
    daily_cost = []
    for date in all_dates:
        day_cost = sum(s["cost"] for s in daily[date].values())
        day_tokens = sum(s["totalTokens"] for s in daily[date].values())
        day_calls = sum(s["calls"] for s in daily[date].values())
        daily_cost.append({
            "date": date,
            "cost": round(day_cost, 6),
            "totalTokens": day_tokens,
            "calls": day_calls,
        })

    # Last N days summaries
    def summarize_days(n):
        cutoff = (now - timedelta(days=n)).strftime("%Y-%m-%d")
        total = {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0,
                 "totalTokens": 0, "cost": 0.0, "calls": 0}
        for date in all_dates:
            if date >= cutoff:
                for stats in daily[date].values():
                    for k in ("input", "output", "cacheRead", "cacheWrite", "totalTokens", "calls"):
                        total[k] += stats[k]
                    total["cost"] += stats["cost"]
        total["cost"] = round(total["cost"], 6)
        return total

    # Today's stats
    today_stats = {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0,
                   "totalTokens": 0, "cost": 0.0, "calls": 0}
    if today in daily:
        for stats in daily[today].values():
            for k in ("input", "output", "cacheRead", "cacheWrite", "totalTokens", "calls"):
                today_stats[k] += stats[k]
            today_stats["cost"] += stats["cost"]
    today_stats["cost"] = round(today_stats["cost"], 6)
    today_stats["cacheHitRate"] = round(
        today_stats["cacheRead"] / max(today_stats["input"] + today_stats["cacheRead"], 1), 4
    )

    # Today's intraday: 48 half-hour slots, per model
    # Slot labels: "00:00", "00:30", "01:00", ..., "23:30"
    slot_labels = [f"{h:02d}:{m:02d}" for h in range(24) for m in (0, 30)]

    today_intraday_models = sorted(
        {model for slot_data in intraday.get(today, {}).values() for model in slot_data}
    )
    # Sort by total tokens descending
    today_intraday_models.sort(
        key=lambda m: -sum(intraday[today][s].get(m, 0) for s in intraday.get(today, {}))
    )

    today_intraday = {
        "slots": slot_labels,
        "byModel": {
            model: [intraday[today][s].get(model, 0) for s in range(48)]
            for model in today_intraday_models
        },
    }

    return {
        "generatedAt": now.isoformat(),
        "timezone": "Asia/Shanghai",
        "dailyByModel": daily_by_model,
        "dailyCost": daily_cost,
        "modelTotals": model_totals_list,
        "last7Days": summarize_days(7),
        "last30Days": summarize_days(30),
        "today": today_stats,
        "todayIntraday": today_intraday,
    }


def main():
    daily, intraday = aggregate()
    output = build_output(daily, intraday)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / "daily_usage.json"
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"Written to {out_path}")


if __name__ == "__main__":
    main()
