"""
Background monitor — checks system health every 60s and sends Telegram alerts.
Also sends a daily summary at a configured hour.
"""

import asyncio
import logging
import os
import subprocess
import urllib.request
from datetime import datetime
from typing import Callable, Awaitable

logger = logging.getLogger(__name__)


class Monitor:
    def __init__(self, send_fn: Callable[[str], Awaitable[None]]):
        """
        send_fn: async function that takes a plain text (or Markdown) message
                 and sends it to the user via Telegram.
        """
        self.send = send_fn
        self._alerted: set[str] = set()   # active alert keys (prevents repeat spam)
        self._last_ip: str | None = None
        self._summary_date = None

    def _run(self, cmd: str) -> tuple[str, str, int]:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=15
        )
        return result.stdout, result.stderr, result.returncode

    # ── Main loop ─────────────────────────────────────────────────────────────

    async def run(self):
        logger.info("Monitor started (interval: 60s)")
        while True:
            try:
                await self._check_all()
            except Exception:
                logger.exception("Monitor check error")
            await asyncio.sleep(60)

    async def _check_all(self):
        await self._check_cpu()
        await self._check_disk()
        await self._check_containers()
        await self._check_public_ip()
        await self._check_daily_summary()

    # ── CPU ───────────────────────────────────────────────────────────────────

    async def _check_cpu(self):
        try:
            stdout, _, _ = self._run("nproc")
            cores = int(stdout.strip() or "4")
            stdout, _, _ = self._run("cat /proc/loadavg")
            load_1m = float(stdout.split()[0])
            pct = (load_1m / cores) * 100

            key = "cpu"
            if pct > 80 and key not in self._alerted:
                self._alerted.add(key)
                await self.send(
                    f"⚠️ *High CPU*: {pct:.0f}% (load {load_1m:.2f} across {cores} cores)"
                )
            elif pct <= 70 and key in self._alerted:
                self._alerted.discard(key)
                await self.send(f"✅ *CPU back to normal*: {pct:.0f}%")
        except Exception:
            logger.warning("CPU check failed", exc_info=True)

    # ── Disk ──────────────────────────────────────────────────────────────────

    async def _check_disk(self):
        try:
            stdout, _, _ = self._run("df -h --output=target,pcent | tail -n +2")
            for line in stdout.strip().splitlines():
                parts = line.split()
                if len(parts) < 2:
                    continue
                mount, pct_str = parts[0], parts[1].rstrip("%")
                try:
                    pct = int(pct_str)
                except ValueError:
                    continue

                key = f"disk:{mount}"
                if pct > 90 and key not in self._alerted:
                    self._alerted.add(key)
                    await self.send(f"⚠️ *Disk almost full*: `{mount}` is at {pct}%")
                elif pct <= 80 and key in self._alerted:
                    self._alerted.discard(key)
                    await self.send(f"✅ *Disk back to normal*: `{mount}` is at {pct}%")
        except Exception:
            logger.warning("Disk check failed", exc_info=True)

    # ── Docker containers ─────────────────────────────────────────────────────

    async def _check_containers(self):
        try:
            stdout, _, rc = self._run(
                "docker ps -a --format '{{.Names}}\t{{.Status}}'"
            )
            if rc != 0:
                return
            for line in stdout.strip().splitlines():
                parts = line.split("\t")
                if len(parts) < 2:
                    continue
                name, status = parts[0], parts[1]
                key = f"container:{name}"
                is_down = status.startswith("Exited") or status.startswith("Dead")

                if is_down and key not in self._alerted:
                    self._alerted.add(key)
                    await self.send(
                        f"🔴 *Container down*: `{name}`\nStatus: {status}"
                    )
                elif not is_down and key in self._alerted:
                    self._alerted.discard(key)
                    await self.send(f"🟢 *Container recovered*: `{name}`")
        except Exception:
            logger.warning("Container check failed", exc_info=True)

    # ── Public IP ─────────────────────────────────────────────────────────────

    async def _check_public_ip(self):
        try:
            new_ip = ""
            try:
                with urllib.request.urlopen("https://ifconfig.me", timeout=5) as r:
                    new_ip = r.read().decode().strip()
            except Exception:
                return

            if self._last_ip is None:
                self._last_ip = new_ip
                return

            if new_ip and new_ip != self._last_ip:
                old_ip = self._last_ip
                self._last_ip = new_ip
                await self.send(
                    f"🌐 *Public IP changed*\nOld: `{old_ip}`\nNew: `{new_ip}`"
                )
        except Exception:
            logger.warning("IP check failed", exc_info=True)

    # ── Daily summary ─────────────────────────────────────────────────────────

    async def _check_daily_summary(self):
        try:
            now = datetime.now()
            summary_hour = int(os.getenv("SUMMARY_HOUR", "8"))
            today = now.date()

            if now.hour == summary_hour and self._summary_date != today:
                self._summary_date = today
                from agent import ask
                report = await ask(
                    "Give me a brief daily summary: overall system health, "
                    "resource usage, and Docker container status. Be concise."
                )
                await self.send(f"📊 *Daily Summary — {today}*\n\n{report}")
        except Exception:
            logger.warning("Daily summary failed", exc_info=True)
