"""
Core agent logic — shared by the Telegram bot and web API.
"""

import os
import anthropic
from tools import TOOL_SCHEMAS, dispatch

SYSTEM_PROMPT = """You are a Raspberry Pi system administrator assistant running
directly on the Pi. You can check system health, inspect Docker containers,
review resource usage, tail logs, and run safe read-only commands.

Guidelines:
- Gather all needed information before writing your final response.
- Be concise but thorough. Use bullet points and clear sections.
- Highlight issues, warnings, or anomalies prominently.
- Flag resource usage above 80% utilization.
- If a container is stopped or a service is failing, say so clearly.
- Never attempt destructive operations.
"""

_client: anthropic.AsyncAnthropic | None = None


def get_client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    return _client


async def ask(prompt: str, history: list | None = None) -> str:
    """
    Run the agent loop for a single user prompt.
    history: list of prior {"role", "content"} messages for multi-turn context.
    Returns the final text response.
    """
    client = get_client()
    messages = list(history or []) + [{"role": "user", "content": prompt}]

    while True:
        response = await client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=TOOL_SCHEMAS,
            messages=messages,
        )

        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "end_turn":
            return "".join(
                block.text for block in response.content if block.type == "text"
            )

        if response.stop_reason == "tool_use":
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    result = dispatch(block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })
            messages.append({"role": "user", "content": tool_results})
            continue

        # Unexpected stop reason
        texts = [b.text for b in response.content if b.type == "text"]
        return "\n".join(texts) if texts else "(no response)"
