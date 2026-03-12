# Pi Agent

An AI-powered Raspberry Pi assistant that monitors system health, Docker containers, resources, and logs — accessible via **Telegram bot** and **REST API**.

Powered by [Claude](https://anthropic.com) (Anthropic) running directly on the Pi using subprocess — no SSH overhead, no always-on Mac required.

## Features

- **Telegram bot** — ask anything in natural language, use built-in commands
- **REST API** — query programmatically from any device on your network
- **Runs on the Pi** — installs as a systemd service, starts on boot
- **AI-powered** — Claude reasons about what to check and interprets the results
- **Allowlisted commands** — only safe, read-only shell commands are permitted

## What it can check

| Tool | Description |
|---|---|
| System info | Hostname, OS, kernel, CPU, temperature |
| Resource usage | RAM, CPU load, top processes, disk space |
| Docker status | All containers, per-container CPU/mem/net, disk usage |
| Service status | Any systemd service (nginx, ssh, docker, etc.) |
| Logs | journalctl or `docker logs` for any service/container |
| Run command | Arbitrary shell commands from the allowlist |

## Telegram commands

| Command | Description |
|---|---|
| `/status` | Full system report |
| `/docker` | Docker container overview |
| `/help` | Show available commands |
| Any text | Free-form question to the AI |

## REST API

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

## Setup

### Prerequisites

- Raspberry Pi running Raspberry Pi OS (or any Debian-based distro)
- Python 3.10+
- An [Anthropic API key](https://console.anthropic.com) with credits
- A Telegram bot token from [@BotFather](https://t.me/BotFather)

### Install

```bash
# Clone the repo
git clone https://github.com/yourusername/pi-agent ~/pi-agent
cd ~/pi-agent

# Create virtualenv and install dependencies
python3 -m venv venv
venv/bin/pip install -r requirements.txt

# Configure
cp .env.example .env
nano .env  # fill in your keys
```

### Configuration (`.env`)

```env
ANTHROPIC_API_KEY=sk-ant-...

TELEGRAM_BOT_TOKEN=123456:ABC...
TELEGRAM_ALLOWED_CHAT_IDS=123456789  # your Telegram chat ID (@userinfobot)

API_HOST=0.0.0.0
API_PORT=9000
API_KEY=your_secret_key
```

### Run as a systemd service

```bash
# Install and enable
sudo cp pi-agent.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now pi-agent

# Check status
sudo systemctl status pi-agent

# View logs
sudo journalctl -u pi-agent -f
```

## Project structure

```
pi-agent/
├── main.py              # Entry point — runs bot + API concurrently
├── agent.py             # Core Claude agent loop (shared by bot and API)
├── tools.py             # Tool implementations via subprocess + Claude schemas
├── bot.py               # Telegram bot handlers
├── api.py               # FastAPI web API
├── pi-agent.service     # systemd unit file
├── requirements.txt
└── .env.example
```

## Adding allowed commands

Edit `ALLOWED_COMMAND_PREFIXES` in `tools.py` to expand or restrict what the `run_command` tool can execute. Any command that doesn't start with a listed prefix will be rejected.

## License

MIT
