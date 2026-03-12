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
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from agent import ask

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
        "  /status — system overview\n"
        "  /docker — Docker containers\n"
        "  /help   — this message\n\n"
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
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    return app
