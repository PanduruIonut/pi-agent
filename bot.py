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
from tools import restart_docker_container

logger = logging.getLogger(__name__)

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


async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "cancel":
        await query.edit_message_text("Cancelled.")
        return

    if query.data.startswith("restart:"):
        container = query.data[8:]
        await query.edit_message_text(f"Restarting `{container}`…", parse_mode="Markdown")
        result = restart_docker_container(container)
        await query.edit_message_text(result)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not authorized(update):
        await update.message.reply_text("⛔ Not authorized.")
        return

    user_text = update.message.text.strip()
    if not user_text:
        return

    await update.message.reply_text("Thinking…")
    try:
        response = await ask(user_text)
        await send(update, response)
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
    app.add_handler(CommandHandler("network", cmd_network))
    app.add_handler(CommandHandler("ports", cmd_ports))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    return app
