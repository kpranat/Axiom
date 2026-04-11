import os
from typing import Tuple

from groq import Groq
from dotenv import load_dotenv

load_dotenv()

client = Groq(api_key=os.getenv("GROQ_API_KEY"))


def summarize(messages: list[dict]) -> Tuple[str, int]:
    """
    Summarises a list of conversation messages into a compact 5-sentence summary
    using Groq (llama-3.1-8b-instant) and returns the summary alongside the number of tokens saved.

    Args:
        messages: A list of dicts with keys 'role' and 'content'.

    Returns:
        Tuple of (summary: str, tokens_saved: int)
    """
    history_text = "\n".join(
        f"{m['role'].upper()}: {m['content']}" for m in messages
    )

    resp = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a conversation summariser. "
                    "Output ONLY the summary itself — no preamble, no labels, no intro phrases. "
                    "Never start with 'Here is', 'Here are', 'Summary:', 'The following', or any similar opener. "
                    "Begin directly with the first factual sentence of the summary."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Summarize the conversation below in exactly 5 sentences. "
                    f"Keep only important facts and decisions.\n\n{history_text}"
                ),
            },
        ],
        max_tokens=250,
    )

    summary = resp.choices[0].message.content
    tokens_saved = resp.usage.prompt_tokens - resp.usage.completion_tokens
    return summary, max(tokens_saved, 0)
