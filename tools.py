"""
Tool definitions for the Pi agent.
Runs commands locally via subprocess (no SSH needed — this runs on the Pi itself).
"""

import os
import subprocess
import urllib.request
from typing import Tuple

# Commands (or prefixes) permitted by run_command.
# A submitted command must START WITH one of these prefixes.
ALLOWED_COMMAND_PREFIXES = [
    # System info
    "uptime", "hostname", "uname", "whoami", "who", "last", "w",
    "date", "timedatectl",
    # Resources
    "free", "df", "du -sh", "lsblk", "vmstat", "iostat", "mpstat",
    "top -b", "ps aux", "ps -ef",
    # Raspberry Pi specific
    "vcgencmd", "pinctrl", "raspi-config nonint",
    # Docker (read-only)
    "docker ps", "docker stats --no-stream", "docker logs",
    "docker inspect", "docker images", "docker info",
    "docker version", "docker network ls", "docker network inspect",
    "docker volume ls", "docker compose ps", "docker compose logs",
    # Services
    "systemctl status", "systemctl list-units", "service --status-all",
    "journalctl",
    # Network
    "ip addr", "ip route", "ip link", "ip neigh",
    "netstat", "ss", "ping -c", "nslookup", "dig",
    "curl -s", "wget -q",
    # Files / logs (read-only)
    "cat /proc/cpuinfo", "cat /proc/meminfo", "cat /proc/loadavg",
    "cat /etc/os-release", "cat /etc/hostname",
    "ls ", "find ", "tail ", "head ", "grep ",
    "dmesg",
]


def _run(cmd: str, timeout: int = 30) -> Tuple[str, str, int]:
    """Run a shell command locally. Returns (stdout, stderr, exit_code)."""
    result = subprocess.run(
        cmd, shell=True, capture_output=True, text=True, timeout=timeout
    )
    return result.stdout, result.stderr, result.returncode


def is_command_allowed(command: str) -> bool:
    cmd = command.strip()
    return any(cmd.startswith(prefix) for prefix in ALLOWED_COMMAND_PREFIXES)


# ── Tool implementations ──────────────────────────────────────────────────────

def get_system_info() -> str:
    parts = {}
    for label, cmd in [
        ("uptime",      "uptime"),
        ("hostname",    "hostname -f 2>/dev/null || hostname"),
        ("os",          "grep PRETTY_NAME /etc/os-release | cut -d= -f2 | tr -d '\"'"),
        ("kernel",      "uname -r"),
        ("cpu",         "grep 'model name' /proc/cpuinfo | head -1 | cut -d: -f2"),
        ("arch",        "uname -m"),
    ]:
        stdout, _, _ = _run(cmd)
        parts[label] = stdout.strip()

    stdout, _, rc = _run("vcgencmd measure_temp 2>/dev/null")
    if rc == 0 and stdout.strip():
        parts["temperature"] = stdout.strip()

    return "\n".join(f"{k}: {v}" for k, v in parts.items() if v)


def get_resource_usage() -> str:
    results = []

    stdout, _, _ = _run("free -h")
    results.append("=== Memory ===\n" + stdout.strip())

    stdout, _, _ = _run("cat /proc/loadavg")
    results.append("=== CPU Load (1m 5m 15m) ===\n" + stdout.strip())

    stdout, _, _ = _run("ps aux --sort=-%cpu | head -11")
    results.append("=== Top Processes by CPU ===\n" + stdout.strip())

    stdout, _, _ = _run("df -h")
    results.append("=== Disk Usage ===\n" + stdout.strip())

    return "\n\n".join(results)


def get_docker_status() -> str:
    results = []

    stdout, stderr, rc = _run(
        "docker ps -a --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'"
    )
    if rc != 0:
        return f"Docker not available or permission denied: {stderr.strip()}"
    results.append("=== Containers ===\n" + stdout.strip())

    stdout, _, rc = _run(
        "docker stats --no-stream --format 'table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}'"
    )
    if rc == 0 and stdout.strip():
        results.append("=== Resource Usage ===\n" + stdout.strip())

    stdout, _, rc = _run("docker system df 2>/dev/null")
    if rc == 0 and stdout.strip():
        results.append("=== Docker Disk Usage ===\n" + stdout.strip())

    return "\n\n".join(results)


def get_service_status(service_name: str) -> str:
    stdout, stderr, rc = _run(f"systemctl status {service_name} --no-pager -l")
    if rc not in (0, 3):
        return f"Error: {stderr.strip() or stdout.strip()}"
    return stdout.strip() or stderr.strip()


def get_logs(source: str, lines: int = 50) -> str:
    """
    source: systemd service name (e.g. 'nginx')
            or 'docker:container_name' for Docker logs
    """
    if source.startswith("docker:"):
        container = source[7:]
        cmd = f"docker logs --tail {lines} {container} 2>&1"
    else:
        cmd = f"journalctl -u {source} -n {lines} --no-pager"

    stdout, stderr, rc = _run(cmd)
    if rc != 0 and not stdout:
        return f"Error: {stderr.strip()}"
    return stdout.strip()


def run_command(command: str) -> str:
    if not is_command_allowed(command):
        return (
            f"Command not allowed: '{command}'\n"
            "Only safe read-only commands are permitted."
        )
    stdout, stderr, rc = _run(command)
    output = stdout
    if stderr.strip():
        output += f"\n[stderr]: {stderr.strip()}"
    if rc != 0:
        output += f"\n[exit code: {rc}]"
    return output.strip() or "(no output)"


# ── Claude tool schemas ───────────────────────────────────────────────────────

TOOL_SCHEMAS = [
    {
        "name": "get_system_info",
        "description": (
            "Get general system information: hostname, OS, kernel version, "
            "CPU model, architecture, and temperature (Raspberry Pi)."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_resource_usage",
        "description": (
            "Get current resource usage: memory, CPU load averages, "
            "top processes by CPU, and disk space for all partitions."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_docker_status",
        "description": (
            "Get Docker container status: all containers (running/stopped), "
            "per-container CPU/memory/network usage, and Docker disk usage."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_service_status",
        "description": "Check the status of a systemd service (e.g. nginx, ssh, docker, cron).",
        "input_schema": {
            "type": "object",
            "properties": {
                "service_name": {
                    "type": "string",
                    "description": "Systemd service name, e.g. 'nginx' or 'docker'",
                }
            },
            "required": ["service_name"],
        },
    },
    {
        "name": "get_logs",
        "description": (
            "Retrieve recent log lines from a systemd service or Docker container. "
            "For systemd use the service name (e.g. 'nginx'). "
            "For Docker prefix with 'docker:' (e.g. 'docker:my_container')."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "source": {
                    "type": "string",
                    "description": "Service name or 'docker:container_name'",
                },
                "lines": {
                    "type": "integer",
                    "description": "Number of log lines to return (default 50)",
                    "default": 50,
                },
            },
            "required": ["source"],
        },
    },
    {
        "name": "get_docker_logs_filtered",
        "description": "Get recent Docker container logs filtered to only show errors, warnings, exceptions, and fatal messages.",
        "input_schema": {
            "type": "object",
            "properties": {
                "container": {"type": "string", "description": "Container name"},
                "lines": {"type": "integer", "description": "Number of recent log lines to scan (default 200)", "default": 200},
            },
            "required": ["container"],
        },
    },
    {
        "name": "get_network_devices",
        "description": "Scan the local network and list all connected devices with their IP and MAC addresses.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_exposed_ports",
        "description": "List all listening/exposed ports on this system and which processes own them.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_public_ip",
        "description": "Get the current public IP address of this machine.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_temperatures",
        "description": "Get CPU and GPU temperatures and throttling status (Raspberry Pi).",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_top_processes",
        "description": "Get the top 10 processes by CPU usage and top 10 by memory usage.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_disk_breakdown",
        "description": "Get disk partition usage and per-directory size breakdown for key paths.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "run_backup",
        "description": "Backup Pi data (docker-services and pi-agent) to the SSD using rsync.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "run_command",
        "description": (
            "Run a shell command on the Pi. Only safe read-only commands "
            "from the allowlist are permitted. Destructive commands are rejected."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command to run"}
            },
            "required": ["command"],
        },
    },
]


def get_temperatures() -> str:
    results = []
    stdout, _, rc = _run("vcgencmd measure_temp 2>/dev/null")
    if rc == 0 and stdout.strip():
        results.append(f"GPU: {stdout.strip()}")
    stdout, _, _ = _run("cat /sys/class/thermal/thermal_zone*/temp 2>/dev/null")
    if stdout.strip():
        for i, t in enumerate(stdout.strip().splitlines()):
            try:
                results.append(f"CPU zone {i}: {int(t) / 1000:.1f}°C")
            except ValueError:
                pass
    stdout, _, rc = _run("vcgencmd get_throttled 2>/dev/null")
    if rc == 0 and stdout.strip():
        results.append(f"Throttle status: {stdout.strip()}")
        try:
            val = int(stdout.strip().split("=")[1], 16)
            flags = []
            if val & 0x1: flags.append("under-voltage")
            if val & 0x2: flags.append("arm freq capped")
            if val & 0x4: flags.append("currently throttled")
            if val & 0x8: flags.append("soft temp limit active")
            if flags:
                results.append(f"⚠️ Active flags: {', '.join(flags)}")
        except Exception:
            pass
    return "\n".join(results) if results else "Temperature data not available."


def get_top_processes() -> str:
    results = []
    stdout, _, _ = _run("ps aux --sort=-%cpu | head -11")
    results.append("=== Top by CPU ===\n" + stdout.strip())
    stdout, _, _ = _run("ps aux --sort=-%mem | head -11")
    results.append("=== Top by Memory ===\n" + stdout.strip())
    return "\n\n".join(results)


def get_disk_breakdown() -> str:
    results = []
    stdout, _, _ = _run("df -h")
    results.append("=== Partitions ===\n" + stdout.strip())
    breakdown = []
    for path in ["/home", "/var/lib/docker", "/var/log", "/tmp", "/root"]:
        stdout, _, rc = _run(f"du -sh {path} 2>/dev/null")
        if rc == 0 and stdout.strip():
            breakdown.append(stdout.split()[0] + f"  {path}")
    if breakdown:
        results.append("=== Directory sizes ===\n" + "\n".join(breakdown))
    return "\n\n".join(results)


def run_backup() -> str:
    dest_root = os.getenv("BACKUP_DEST", "/mnt/ssd/pi-backup")
    sources_raw = os.getenv("BACKUP_SOURCES", "/home/pi/docker-services,/home/pi/pi-agent")
    sources = [s.strip() for s in sources_raw.split(",") if s.strip()]

    stdout, _, _ = _run(f"test -d {dest_root} && echo ok")
    if "ok" not in stdout:
        return f"❌ Backup destination not found: `{dest_root}`\nMake sure the SSD is mounted and set BACKUP_DEST in .env"

    from datetime import datetime
    dest = f"{dest_root}/{datetime.now().strftime('%Y-%m-%d_%H-%M')}"
    _run(f"mkdir -p {dest}")

    results = []
    for src in sources:
        stdout, stderr, rc = _run(f"rsync -a --delete {src} {dest}/", timeout=300)
        name = src.rstrip("/").split("/")[-1]
        if rc == 0:
            results.append(f"✅ {name}")
        else:
            results.append(f"❌ {name}: {(stderr or stdout).strip()[:200]}")

    return f"Backup → `{dest}`\n" + "\n".join(results)


def get_docker_cleanup_preview() -> str:
    stdout, _, _ = _run("docker system df")
    return stdout.strip()


def docker_prune_dangling() -> str:
    results = []
    for cmd, label in [
        ("docker container prune -f", "Stopped containers"),
        ("docker image prune -f", "Dangling images"),
        ("docker network prune -f", "Unused networks"),
        ("docker builder prune -f", "Build cache"),
    ]:
        stdout, stderr, rc = _run(cmd)
        results.append(f"{label}: {'OK' if rc == 0 else 'error — ' + stderr.strip()}\n{stdout.strip()}")
    return "\n\n".join(results)


def docker_prune_all() -> str:
    stdout, stderr, rc = _run("docker system prune -a -f")
    if rc != 0:
        return f"Error: {stderr.strip()}"
    return stdout.strip()


def restart_docker_container(container_name: str) -> str:
    # Verify container exists first
    stdout, _, rc = _run(f"docker ps -a --format '{{{{.Names}}}}' | grep -x '{container_name}'")
    if rc != 0 or not stdout.strip():
        return f"Container '{container_name}' not found."
    stdout, stderr, rc = _run(f"docker restart {container_name}")
    if rc != 0:
        return f"Failed to restart '{container_name}': {stderr.strip()}"
    return f"✅ Container '{container_name}' restarted successfully."


def get_docker_logs_filtered(container: str, lines: int = 200) -> str:
    stdout, stderr, rc = _run(f"docker logs --tail {lines} {container} 2>&1")
    if rc != 0 and not stdout:
        return f"Error: {stderr.strip()}"
    keywords = ("error", "warn", "exception", "fatal", "critical", "traceback", "panic")
    filtered = [l for l in stdout.splitlines() if any(kw in l.lower() for kw in keywords)]
    if not filtered:
        return f"No errors or warnings found in the last {lines} lines of '{container}'."
    return f"{len(filtered)} error/warning lines in '{container}':\n\n" + "\n".join(filtered[-50:])


def get_network_devices() -> str:
    # Try arp-scan first (more detailed), fall back to arp -a
    stdout, _, rc = _run("sudo arp-scan --localnet 2>/dev/null")
    if rc != 0 or not stdout.strip():
        stdout, _, _ = _run("arp -a")
    return stdout.strip() or "No devices found."


def get_exposed_ports() -> str:
    stdout, _, _ = _run("ss -tlnp")
    return stdout.strip()


def get_public_ip() -> str:
    try:
        with urllib.request.urlopen("https://ifconfig.me", timeout=5) as r:
            return r.read().decode().strip()
    except Exception:
        try:
            with urllib.request.urlopen("https://api.ipify.org", timeout=5) as r:
                return r.read().decode().strip()
        except Exception as e:
            return f"Could not determine public IP: {e}"


def dispatch(tool_name: str, tool_input: dict) -> str:
    match tool_name:
        case "get_system_info":
            return get_system_info()
        case "get_resource_usage":
            return get_resource_usage()
        case "get_docker_status":
            return get_docker_status()
        case "get_service_status":
            return get_service_status(tool_input["service_name"])
        case "get_logs":
            return get_logs(tool_input["source"], tool_input.get("lines", 50))
        case "run_command":
            return run_command(tool_input["command"])
        case "get_temperatures":
            return get_temperatures()
        case "get_top_processes":
            return get_top_processes()
        case "get_disk_breakdown":
            return get_disk_breakdown()
        case "run_backup":
            return run_backup()
        case "get_docker_logs_filtered":
            return get_docker_logs_filtered(tool_input["container"], tool_input.get("lines", 200))
        case "get_network_devices":
            return get_network_devices()
        case "get_exposed_ports":
            return get_exposed_ports()
        case "get_public_ip":
            return get_public_ip()
        case _:
            return f"Unknown tool: {tool_name}"
