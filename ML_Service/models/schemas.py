from typing import Optional
from pydantic import BaseModel, Field


class Message(BaseModel):
    """Represents a single chat message."""

    role: str = Field(..., description="The role of the message sender (user, assistant, system).")
    content: str = Field(..., description="The text content of the message.")


class SummariseRequest(BaseModel):
    """Request body for the /summarise endpoint."""

    messages: list[Message] = Field(
        ...,
        description="A list of conversation messages to summarise.",
        min_length=1,
    )


class SummariseResponse(BaseModel):
    """Response body returned by the /summarise endpoint."""

    summary: str = Field(..., description="A 5-sentence summary of the conversation.")
    tokens_saved: int = Field(..., description="Estimated number of tokens saved by summarising.")


# ──────────────────────────────────────────────────────────────────────────────
# Semantic cache schemas
# ──────────────────────────────────────────────────────────────────────────────

class QueryRequest(BaseModel):
    """Request body for POST /cache/query."""

    prompt: str = Field(
        ...,
        description="The natural-language query to process through the semantic cache.",
        min_length=1,
    )
    user_id: str = Field(
        ...,
        description="Unique identifier for the requesting user (used for the personal cache layer).",
        min_length=1,
    )


class QueryResponse(BaseModel):
    """Response body returned by POST /cache/query."""

    response: str = Field(..., description="The answer — from cache or LLM.")
    cache_layer: str = Field(
        ...,
        description="Which layer served the response: 'global', 'personal', or 'miss' (LLM called).",
    )
    classified: str = Field(
        ...,
        description="Classification of the prompt: 'PERSONAL' or 'GENERIC'.",
    )
    score: Optional[float] = Field(
        None,
        description="Cosine similarity score of the cache hit (None on LLM call).",
    )


class CacheStatsResponse(BaseModel):
    """Response body returned by GET /cache/stats."""

    global_entries: int = Field(..., description="Number of entries in the global FAISS store.")
    user_stores: dict[str, int] = Field(
        ...,
        description="Mapping of user_id -> number of entries in their personal FAISS store.",
    )
