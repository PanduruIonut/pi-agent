"""
Telegram bot interface for the Pi agent.

Commands:
  /start   — welcome message
  /status  — quick system overview (info + resources)
  /docker  — Docker container status
  /help    — show available commands

Any other text is forwarded to the AI agent as a free-form question.
"""

import os
import logging
import subprocess
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from agent import ask
from tools import restart_docker_container, get_docker_cleanup_preview, docker_prune_dangling, docker_prune_all

logger = logging.getLogger(__name__)

# Per-chat conversation history (chat_id → message list)
_chat_history: dict[int, list] = {}
HISTORY_MAX = 20  # messages (10 turns)

TELEGRAM_MAX_LENGTH = 4096  # Telegram's message length limit


def get_allowed_ids() -> set[int]:
    raw = os.getenv("TELEGRAM_ALLOWED_CHAT_IDS", "")
    ids = set()
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit():
            ids.add(int(part))
    return ids


def authorized(update: Update) -> bool:
    allowed = get_allowed_ids()
    if not allowed:
        return True  # No restriction configured — allow all (not recommended for production)
    return update.effective_chat.id in allowed


def split_message(text: str) -> list[str]:
    """Split a long message into Telegram-safe chunks."""
    if len(text) <= TELEGRAM_MAX_LENGTH:
        return [text]
    chunks = []
    while text:
        chunks.append(text[:TELEGRAM_MAX_LENGTH])
        text = text[TELEGRAM_MAX_LENGTH:]
    return chunks


async def send(update: Update, text: str):
    for chunk in split_message(text):
        await update.message.reply_text(chunk)


# ── Handlers ─────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not authorized(update):
        return
    await update.message.reply_text(
        "👋 Pi Agent online!\n\n"
        "Commands:\n"
        "  /status           — system overview\n"
        "  /docker           — Docker containers\n"
        "  /restart <name>   — restart a container\n"
        "  /cleanup          — free Docker disk space\n"
        "  /backup           — backup data to SSD\n"
        "  /temps            — CPU/GPU temperatures\n"
        "  /top              — top processes\n"
        "  /disk             — disk usage breakdown\n"
        "  /network          — devices on the network\n"
        "  /ports            — exposed ports\n"
        "  /help             — this message\n\n"
        "Or just ask me anything about your Pi."
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cmd_start(update, context)


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not authorized(update):
        return
    await update.message.reply_text("Checking system status…")
    response = await ask("Give me a full system status report: system info, resource usage, and any issues.")
    await send(update, response)


async def cmd_docker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not authorized(update):
        return
    await update.message.reply_text("Checking Docker…")
    response = await ask("Check all Docker containers. Report their status, resource usage, and flag any that are stopped or unhealthy.")
    await send(update, response)


async def cmd_restart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not authorized(update):
        return
    if not context.args:
        # List running containers to pick from
        result = subprocess.run(
            "docker ps --format '{{.Names}}\t{{.Status}}'",
            shell=True, capture_output=True, text=True
        )
        lines = result.stdout.strip().splitlines()
        if not lines:
            await update.message.reply_text("No running containers found.")
            return
        container_list = "\n".join(f"  • {l.split(chr(9))[0]}" for l in lines)
        await update.message.reply_text(
            f"Usage: `/restart <container_name>`\n\nRunning containers:\n{container_list}",
            parse_mode="Markdown"
        )
        return

    container = context.args[0]
    keyboard = [[
        InlineKeyboardButton("✅ Yes, restart", callback_data=f"restart:{container}"),
        InlineKeyboardButton("❌ Cancel", callback_data="cancel"),
    ]]
    await update.message.reply_text(
        f"Restart container `{container}`?",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )


async def cmd_network(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not authorized(update):
        return
    await update.message.reply_text("Scanning network…")
    response = await ask(
        "Scan the local network for connected devices and list them with IP and MAC. "
        "Also show the current public IP address."
    )
    await send(update, response)


async def cmd_ports(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not authorized(update):
        return
    await update.message.reply_text("Checking exposed ports…")
    response = await ask(
        "List all listening ports on this system. For each port, identify what "
        "service or process is using it."
    )
    await send(update, response)


async def cmd_temps(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not authorized(update):
        return
    response = await ask("Report CPU and GPU temperatures and any throttling issues.")
    await send(update, response)


async def cmd_top(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not authorized(update):
        return
    response = await ask("Show the top processes by CPU and memory usage right now.")
    await send(update, response)


async def cmd_disk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not authorized(update):
        return
    response = await ask("Show disk usage: partition breakdown and which directories are using the most space.")
    await send(update, response)


async def cmd_backup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not authorized(update):
        return
    keyboard = [[
        InlineKeyboardButton("✅ Yes, back up now", callback_data="backup:confirm"),
        InlineKeyboardButton("❌ Cancel", callback_data="cancel"),
    ]]
    await update.message.reply_text(
        "Back up Pi data (docker-services + pi-agent) to the SSD?",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def cmd_cleanup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not authorized(update):
        return
    usage = get_docker_cleanup_preview()
    keyboard = [
        [
            InlineKeyboardButton("🧹 Dangling only", callback_data="cleanup:dangling"),
            InlineKeyboardButton("🗑️ All unused", callback_data="cleanup:all"),
        ],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")],
    ]
    await update.message.reply_text(
        f"*Docker disk usage:*\n```\n{usage}\n```\n\n"
        "Choose cleanup scope:\n"
        "• *Dangling only* — stopped containers, dangling images, unused networks, build cache\n"
        "• *All unused* — everything above + all images not used by a running container",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown",
    )


async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "cancel":
        await query.edit_message_text("Cancelled.")
        return

    if query.data == "backup:confirm":
        await query.edit_message_text("💾 Backing up to SSD…")
        from tools import run_backup
        result = run_backup()
        await query.edit_message_text(result)
        return

    if query.data.startswith("restart:"):
        container = query.data[8:]
        await query.edit_message_text(f"Restarting `{container}`…", parse_mode="Markdown")
        result = restart_docker_container(container)
        await query.edit_message_text(result)

    elif query.data == "cleanup:dangling":
        await query.edit_message_text("🧹 Pruning dangling resources…")
        result = docker_prune_dangling()
        await query.edit_message_text(f"✅ Done:\n\n{result[:3800]}")

    elif query.data == "cleanup:all":
        await query.edit_message_text("🗑️ Pruning all unused resources…")
        result = docker_prune_all()
        await query.edit_message_text(f"✅ Done:\n\n{result[:3800]}")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not authorized(update):
        await update.message.reply_text("⛔ Not authorized.")
        return

    user_text = update.message.text.strip()
    if not user_text:
        return

    chat_id = update.effective_chat.id
    history = _chat_history.get(chat_id, [])

    await update.message.reply_text("Thinking…")
    try:
        response = await ask(user_text, history=history)
        await send(update, response)

        # Store exchange and trim to HISTORY_MAX messages
        history = history + [
            {"role": "user", "content": user_text},
            {"role": "assistant", "content": response},
        ]
        _chat_history[chat_id] = history[-HISTORY_MAX:]
    except Exception as e:
        logger.exception("Agent error")
        await update.message.reply_text(f"Error: {e}")


# ── App factory ───────────────────────────────────────────────────────────────

def build_app() -> Application:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN not set in environment")

    app = (
        Application.builder()
        .token(token)
        .read_timeout(120)
        .write_timeout(120)
        .connect_timeout(30)
        .build()
    )
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("docker", cmd_docker))
    app.add_handler(CommandHandler("restart", cmd_restart))
    app.add_handler(CommandHandler("cleanup", cmd_cleanup))
    app.add_handler(CommandHandler("backup", cmd_backup))
    app.add_handler(CommandHandler("temps", cmd_temps))
    app.add_handler(CommandHandler("top", cmd_top))
    app.add_handler(CommandHandler("disk", cmd_disk))
    app.add_handler(CommandHandler("network", cmd_network))
    app.add_handler(CommandHandler("ports", cmd_ports))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    return app
