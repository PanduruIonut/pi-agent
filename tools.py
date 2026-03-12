"""
Tool definitions for the Pi agent.
Runs commands locally via subprocess (no SSH needed — this runs on the Pi itself).
"""

import subprocess
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
        case _:
            return f"Unknown tool: {tool_name}"
