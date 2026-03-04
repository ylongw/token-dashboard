# 🦞 Token Dashboard

A self-hosted dashboard to visualize AI token consumption from [OpenClaw](https://github.com/openclaw/openclaw) agent sessions and Claude Code (ACP harness).

## Features

- **Daily token usage by model** — stacked bar chart (Claude Opus/Sonnet, GPT Codex, Gemini, etc.)
- **Daily cost by model** — stacked bar chart with pricing fallback table
- **Today's intraday usage** — 30-minute interval line chart, current day only
- **Daily cost trend** — line chart across selectable periods (7/14/30 days, All Time)
- **Model distribution** — doughnut chart (token share)
- **Model breakdown table** — all-time totals with input/output/cache breakdown
- **Cache hit rate** — displayed prominently; helps understand effective cost

## Data Sources

| Source | Path | Notes |
|--------|------|-------|
| OpenClaw sessions | `~/.openclaw/agents/main/sessions/*.jsonl` | Native format with cost data |
| Claude Code (ACP) | `~/.claude/projects/**/*.jsonl` | Deduplicated by `msg_id` (streaming chunks) |

## Architecture

```
OpenClaw sessions  +  Claude Code sessions
         │
         ▼  scripts/aggregate.py  (run hourly via LaunchAgent)
         │
    daily_usage.json
         │
         ▼  server.py  (Python stdlib HTTP, port 8901)
         │
    http://localhost:8901
         │
         ▼  Cloudflare Tunnel  (or any reverse proxy)
         │
    https://your-dashboard.example.com
```

## Requirements

- macOS (uses LaunchAgents for scheduling)
- Python 3.10+ (stdlib only, no pip dependencies)
- OpenClaw with session logging enabled
- `cloudflared` CLI (for Cloudflare Tunnel) — or swap for nginx/caddy/etc.

## Setup

### 1. Clone & configure paths

```bash
git clone https://github.com/ylongw/token-dashboard
cd token-dashboard
```

Edit the three `*.plist` files — replace `${HOME}` with your actual home path if needed.

### 2. Create runtime directory

```bash
mkdir -p ~/.token-dashboard/{data,logs,public,scripts}
cp public/index.html ~/.token-dashboard/public/
cp scripts/aggregate.py ~/.token-dashboard/scripts/
cp server.py ~/.token-dashboard/
```

### 3. Run aggregation

```bash
python3 scripts/aggregate.py
# → writes ~/.token-dashboard/data/daily_usage.json
```

### 4. Start HTTP server

```bash
cd ~/.token-dashboard && python3 server.py
# → http://localhost:8901
```

### 5. Install LaunchAgents (macOS)

```bash
cp com.token-dashboard.*.plist ~/Library/LaunchAgents/
# Edit paths in each plist to match your setup
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.token-dashboard.server.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.token-dashboard.aggregate.plist
```

### 6. Expose via Cloudflare Tunnel (optional)

```bash
# Create a tunnel
cloudflared tunnel create token-dashboard

# Configure (see cloudflared-config.example.yml)
cp cloudflared-config.example.yml ~/.cloudflared/token-dashboard.yml
# Edit: set your tunnel ID and hostname

# Install LaunchAgent
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.token-dashboard.cloudflared.plist
```

## Pricing

When provider-reported cost is zero (e.g. Gemini CLI), costs are calculated from a built-in table:

| Model | Input | Output | Cache Read | Cache Write |
|-------|-------|--------|-----------|-------------|
| Claude Opus 4.6 | $5.00/MTok | $25.00 | $0.50 | $6.25 |
| Claude Sonnet 4.6/4.5 | $3.00 | $15.00 | $0.30 | $3.75 |
| GPT-5.3 Codex | $1.75 | $14.00 | $0.175 | $0 |
| Gemini 3 Pro | $2.00 | $12.00 | $0.50 | $1.00 |
| Gemini 3 Flash | $0.30 | $2.50 | $0.075 | $0.15 |

Update `PRICING` in `scripts/aggregate.py` as model prices change.

## Adding a New Model

1. `scripts/aggregate.py` → `normalize_model()`: add string match → display name
2. `scripts/aggregate.py` → `PRICING`: add pricing entry
3. `public/index.html` → `MODEL_COLORS`: add color hex

## Tech Stack

- **Backend**: Python 3 stdlib (no dependencies)
- **Frontend**: Vanilla JS + [Chart.js 4.x](https://www.chartjs.org/) (CDN) + [Inter](https://fonts.google.com/specimen/Inter) font
- **Scheduling**: macOS LaunchAgents
- **Tunnel**: Cloudflare Tunnel (`cloudflared`)

## License

MIT
