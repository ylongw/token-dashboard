# AGENTS.md — Developer & Agent Guide

> Read this before making changes to the codebase.

## Overview

Single-file Python backend + Chart.js frontend dashboard for visualizing AI token usage from OpenClaw and Claude Code sessions.

**Stack**: Python 3 stdlib · Chart.js 4.x · Cloudflare Tunnel · macOS LaunchAgents

## Two Directories

| Path | Role |
|------|------|
| `~/path/to/token-dashboard/` | Git source — edit code here |
| `~/.token-dashboard/` | Runtime — LaunchAgents run from here (TCC-free) |

**Why?** macOS TCC blocks launchd from accessing `~/Documents/`. Runtime copy in `~/.token-dashboard/` is unrestricted. After editing, copy to runtime:

```bash
cp public/index.html ~/.token-dashboard/public/
cp scripts/aggregate.py ~/.token-dashboard/scripts/
```

## Key Files

| File | Purpose |
|------|---------|
| `scripts/aggregate.py` | Core: scan JSONL → `daily_usage.json` |
| `public/index.html` | Dashboard: Chart.js, all JS inline |
| `server.py` | HTTP server: Python stdlib, port 8901 |
| `com.token-dashboard.server.plist` | LaunchAgent: server (KeepAlive) |
| `com.token-dashboard.aggregate.plist` | LaunchAgent: hourly aggregation |
| `com.token-dashboard.cloudflared.plist` | LaunchAgent: Cloudflare Tunnel (KeepAlive) |
| `cloudflared-config.example.yml` | Tunnel config template |

## Data Pipeline

### aggregate.py

Two-phase scan:

**Phase 1 — OpenClaw sessions** (`~/.openclaw/agents/main/sessions/*.jsonl`)

Format: `{type:"message", message:{role:"assistant", model:"...", usage:{input, output, cacheRead, cacheWrite, totalTokens, cost:{total}}, timestamp}}`

**Phase 2 — Claude Code sessions** (`~/.claude/projects/**/*.jsonl`)

Format: Anthropic native (`input_tokens`, `output_tokens`, `cache_creation_input_tokens`, `cache_read_input_tokens`).

⚠️ **Deduplication required**: Claude Code logs streaming chunks — multiple entries share the same `msg_id` with incrementing `output_tokens`. Only the final entry (highest `output_tokens`) is counted.

Cost is always calculated from the pricing table (Claude Code doesn't report cost).

### Output schema (`daily_usage.json`)

```typescript
{
  generatedAt: string;
  timezone: string;
  today: UsageSummary;
  last7Days: UsageSummary;
  last30Days: UsageSummary;
  dailyByModel: Array<{date, model, input, output, cacheRead, cacheWrite, totalTokens, cost, calls}>;
  dailyCost: Array<{date, cost, totalTokens, calls}>;
  modelTotals: Array<{model, ...UsageSummary}>;
  todayIntraday: {slots: string[48], byModel: {[model]: number[48]}};
}
```

## Common Tasks

### Run aggregation manually
```bash
python3 scripts/aggregate.py
```

### Add a new model
1. `aggregate.py` → `normalize_model()`: add string match → display name
2. `aggregate.py` → `PRICING`: add `$/MTok` rates
3. `index.html` → `MODEL_COLORS`: add hex color

### Add a new chart
1. Edit `public/index.html` — Chart.js code is at the bottom `<script>`
2. Call your render function from `renderCharts()`
3. Data is in `rawData` after fetch

### Restart a LaunchAgent
```bash
launchctl kickstart -k gui/$(id -u)/com.token-dashboard.server
```

### View logs
```bash
tail -f ~/.token-dashboard/logs/server.log
tail -f ~/.token-dashboard/logs/aggregate.log
tail -f ~/.token-dashboard/logs/cloudflared.log
```

## Gotchas

| Issue | Cause | Fix |
|-------|-------|-----|
| launchd can't read files | macOS TCC protects `~/Documents` | Use `~/.token-dashboard/` for runtime |
| Gemini cost = $0 | Gemini CLI doesn't report cost | Built-in `PRICING` table calculates it |
| Claude Code tokens overcounted | Streaming chunks: multiple entries per API call | Dedup by `msg_id`, keep highest `output_tokens` |
| Stale data | Hourly cron hasn't run | `python3 scripts/aggregate.py` manually |
| `translate_path()` 404 | Query strings not stripped | Manual `urlparse` in `server.py` |
