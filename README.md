# 🦞 Token Dashboard

A self-hosted dashboard to visualize AI token consumption from [OpenClaw](https://github.com/openclaw/openclaw) agent sessions and Claude Code (ACP harness).

![Dashboard preview showing daily token usage charts by model](https://raw.githubusercontent.com/ylongw/token-dashboard/main/public/index.html)

## Features

- **Today's intraday usage** — 30-min interval line chart, real-time feel
- **Daily token usage by model** — stacked bar (Claude Opus/Sonnet, GPT Codex, Gemini…)
- **Daily cost by model** — stacked bar with built-in pricing fallback
- **Daily cost trend** — line chart (7/14/30 days / All Time)
- **Model distribution** — doughnut chart
- **Model breakdown table** — all-time totals: input · output · cache read · cost · calls
- **Cache hit rate** — shows how much prompt caching is saving you

## Quick Start

```bash
git clone https://github.com/ylongw/token-dashboard
cd token-dashboard
bash install.sh
# → http://localhost:8901
```

`install.sh` handles everything: runtime directory setup, first aggregation, and LaunchAgent registration (macOS). No pip installs needed.

### Options

```bash
bash install.sh --port 8902 --runtime-dir ~/.my-dashboard
```

## Architecture

```
~/.openclaw/agents/main/sessions/*.jsonl   ← OpenClaw native logs
~/.claude/projects/**/*.jsonl              ← Claude Code / ACP harness logs
              │
              ▼  scripts/aggregate.py  (hourly LaunchAgent)
              │
      ~/.token-dashboard/data/daily_usage.json
              │
              ▼  server.py  (Python stdlib, port 8901)
              │
      http://localhost:8901
              │
              ▼  Cloudflare Tunnel  (optional, or any reverse proxy)
              │
      https://your-dashboard.example.com
```

## Requirements

- **macOS** (LaunchAgents for scheduling — Linux: swap for cron)
- **Python 3.10+** — stdlib only, zero pip dependencies
- **OpenClaw** with session logging enabled

## External Access (Cloudflare Tunnel)

```bash
# 1. Create tunnel
cloudflared tunnel create token-dashboard

# 2. Configure
cp cloudflared-config.example.yml ~/.cloudflared/token-dashboard.yml
# Edit: set your TUNNEL_ID and hostname

# 3. Load LaunchAgent
launchctl bootstrap gui/$(id -u) \
  ~/Library/LaunchAgents/com.token-dashboard.cloudflared.plist
```

No VPS required — Cloudflare handles SSL and global routing automatically.

## Data Sources

| Source | Path | Notes |
|--------|------|-------|
| OpenClaw sessions | `~/.openclaw/agents/main/sessions/*.jsonl` | Cost reported by provider |
| Claude Code (ACP) | `~/.claude/projects/**/*.jsonl` | Deduplicated by `msg_id` (streaming chunks) |

Claude Code logs streaming chunks — multiple entries per API call with the same `msg_id`. The aggregator keeps only the final entry (highest `output_tokens`) to avoid overcounting.

## Pricing Table

When provider-reported cost is zero (e.g. Gemini CLI), costs are calculated from a built-in table ($ per million tokens):

| Model | Input | Output | Cache Read | Cache Write |
|-------|-------|--------|-----------|-------------|
| Claude Opus 4.6 | $5.00 | $25.00 | $0.50 | $6.25 |
| Claude Sonnet 4.6 / 4.5 | $3.00 | $15.00 | $0.30 | $3.75 |
| GPT-5.3 Codex | $1.75 | $14.00 | $0.175 | $0 |
| Gemini 3 Pro | $2.00 | $12.00 | $0.50 | $1.00 |
| Gemini 3 Flash | $0.30 | $2.50 | $0.075 | $0.15 |

Update `PRICING` in `scripts/aggregate.py` as model prices change.

## Customization

### Add a new model
1. `scripts/aggregate.py` → `normalize_model()`: add string match → display name
2. `scripts/aggregate.py` → `PRICING`: add pricing entry (optional)
3. `public/index.html` → `MODEL_COLORS`: add hex color

### Add a new chart
All Chart.js code is in the `<script>` block at the bottom of `public/index.html`. Call your render function from `renderCharts()`. Data is in `rawData` after fetch.

### Manual commands
```bash
# Re-run aggregation
python3 ~/.token-dashboard/scripts/aggregate.py

# Restart server
launchctl kickstart -k gui/$(id -u)/com.token-dashboard.server

# View logs
tail -f ~/.token-dashboard/logs/server.log
tail -f ~/.token-dashboard/logs/aggregate.log
```

## Tech Stack

- **Backend**: Python 3 stdlib (zero dependencies)
- **Frontend**: Vanilla JS + [Chart.js 4.x](https://www.chartjs.org/) (CDN) + [Inter](https://fonts.google.com/specimen/Inter) (Google Fonts)
- **Scheduling**: macOS LaunchAgents
- **Tunnel**: [Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/)

## License

[MIT](LICENSE)
