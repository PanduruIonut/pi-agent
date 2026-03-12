# Pi Agent

An AI-powered Raspberry Pi assistant that monitors system health, Docker containers, resources, and logs — accessible via **Telegram bot** and **REST API**.

Powered by [Claude](https://anthropic.com) (Anthropic) running directly on the Pi using subprocess — no SSH overhead, no always-on Mac required.

## Features

- **Telegram bot** — ask anything in natural language, use built-in commands
- **Conversation history** — follow-up questions work ("which one is using the most?", "restart that one")
- **REST API** — query programmatically from any device on your network (optional, can be disabled)
- **Proactive alerts** — notified automatically with AI diagnosis when something goes wrong
- **Daily summary** — scheduled report every morning (optional)
- **Runs on the Pi** — installs as a systemd service, starts on boot
- **AI-powered** — Claude reasons about what to check and interprets the results
- **Allowlisted commands** — only safe, read-only shell commands permitted by default

---

## Telegram commands

| Command | Description |
|---|---|
| `/status` | Full system report (info, resources, Docker) |
| `/docker` | Docker container overview with resource usage |
| `/restart <name>` | Restart a container (asks for confirmation first) |
| `/cleanup` | Free Docker disk space (dangling or all unused) |
| `/backup` | Rsync docker-services + pi-agent to SSD |
| `/temps` | CPU/GPU temperatures and throttle status |
| `/top` | Top processes by CPU and memory |
| `/disk` | Disk partition usage and directory breakdown |
| `/network` | Devices connected to your LAN + public IP |
| `/ports` | All listening ports with process names |
| `/help` | Show available commands |
| Any text | Free-form question to the AI |

---

## Proactive alerts

The monitor runs every 60 seconds in the background and messages you when:

| Trigger | Threshold |
|---|---|
| High CPU | Load > 80% |
| Disk almost full | Any partition > 90% |
| Container down | Any container exits or dies |
| Public IP changed | Any change detected |

Alerts auto-resolve — you get a follow-up message when things recover.

**Smarter alerts** — when CPU or disk thresholds are breached, Claude automatically diagnoses the root cause and includes an explanation in the alert message.

**Daily summary** is disabled by default. Enable with `DAILY_SUMMARY_ENABLED=true` and configure the hour via `SUMMARY_HOUR` (default: 8am).

---

## REST API

Disabled by default. Enable by setting `API_ENABLED=true` in `.env`.

All endpoints require the `X-API-Key` header.

```bash
# Ask anything
curl -X POST http://raspberrypi.local:9000/ask \
  -H "X-API-Key: your_secret" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Are all my Docker containers running?"}'

# Quick status
curl http://raspberrypi.local:9000/status -H "X-API-Key: your_secret"

# Docker report
curl http://raspberrypi.local:9000/docker -H "X-API-Key: your_secret"

# Health check (no auth)
curl http://raspberrypi.local:9000/health
```

---

## Setup

### Prerequisites

- Raspberry Pi running Raspberry Pi OS (or any Debian-based distro)
- Python 3.10+
- An [Anthropic API key](https://console.anthropic.com) with credits
- A Telegram bot token from [@BotFather](https://t.me/BotFather)
- Your Telegram chat ID (message [@userinfobot](https://t.me/userinfobot))

### Install

```bash
git clone https://github.com/PanduruIonut/pi-agent ~/pi-agent
cd ~/pi-agent

python3 -m venv venv
venv/bin/pip install -r requirements.txt

cp .env.example .env
nano .env
```

### Configuration (`.env`)

```env
ANTHROPIC_API_KEY=sk-ant-...

TELEGRAM_BOT_TOKEN=123456:ABC...
TELEGRAM_ALLOWED_CHAT_IDS=123456789

# Web API (disabled by default)
API_ENABLED=false
API_HOST=0.0.0.0
API_PORT=9000
API_KEY=your_secret_key

# Daily summary (set DAILY_SUMMARY_ENABLED=true to enable)
SUMMARY_HOUR=8
DAILY_SUMMARY_ENABLED=false

# Backup — SSD mount point and source directories
BACKUP_DEST=/mnt/ssd/pi-backup
BACKUP_SOURCES=/home/pi/docker-services,/home/pi/pi-agent
```

### Run as a systemd service

```bash
sudo cp pi-agent.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now pi-agent

# Check status
sudo systemctl status pi-agent

# View logs
sudo journalctl -u pi-agent -f
```

---

## Project structure

```
pi-agent/
├── main.py              # Entry point — runs bot, API, and monitor concurrently
├── agent.py             # Core Claude agent loop (shared by bot and API)
├── tools.py             # Tool implementations via subprocess + Claude schemas
├── monitor.py           # Background monitor — alerts and daily summary
├── bot.py               # Telegram bot handlers
├── api.py               # FastAPI web API
├── pi-agent.service     # systemd unit file
├── requirements.txt
└── .env.example
```

---

## What Claude can check

| Tool | Description |
|---|---|
| System info | Hostname, OS, kernel, CPU, temperature |
| Resource usage | RAM, CPU load, top processes, disk space |
| Temperatures | CPU/GPU temps and Pi throttle status |
| Top processes | Top 10 by CPU and memory |
| Disk breakdown | Partition usage + per-directory sizes |
| Docker status | All containers, per-container CPU/mem/net |
| Docker logs (filtered) | Errors, warnings, and exceptions only |
| Service status | Any systemd service |
| Logs | journalctl or `docker logs` |
| Network devices | ARP scan of local network |
| Exposed ports | Listening ports with process names |
| Public IP | Current external IP address |
| Backup | Rsync sources to SSD |
| Run command | Shell commands from the allowlist |

---

## Extending

**Add allowed commands** — edit `ALLOWED_COMMAND_PREFIXES` in `tools.py`. Any command not starting with a listed prefix is rejected.

**Change alert thresholds** — edit `_check_cpu` and `_check_disk` in `monitor.py`.

**Add new tools** — add an implementation in `tools.py`, a schema to `TOOL_SCHEMAS`, a case to `dispatch()`, and Claude will automatically use it.

---

## License

MIT
