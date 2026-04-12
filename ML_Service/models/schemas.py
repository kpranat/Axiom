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


class ClassifyRequest(BaseModel):
    """Request body for the /classify endpoint."""

    prompt: str = Field(
        ...,
        description="The latest user message to classify.",
        min_length=1,
    )


class ClassifyResponse(BaseModel):
    """Response body returned by the /classify endpoint."""

    needs_context: bool = Field(
        ...,
        description="True if the prompt requires prior conversation history to answer correctly.",
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Classifier confidence in the decision (0.0 – 1.0).",
    )
    reason: str = Field(
        ...,
        description="Short explanation of the strongest signal that drove the decision.",
    )


class RouteRequest(BaseModel):
    """Request body for the /route/ endpoint."""

    prompt: str = Field(
        ...,
        description="The latest user message (raw, post-cache-miss).",
        min_length=1,
    )
    context: str | None = Field(
        default=None,
        description=(
            "Optional pre-summarised conversation history "
            "(output of the /summarise endpoint). "
            "Included verbatim in the final prompt_to_send if provided."
        ),
    )
    user_id: str = Field(
        ...,
        description="Identifier of the user — used for audit / future personalisation.",
    )


class RouteResponse(BaseModel):
    """Response body returned by the /route/ endpoint."""

    prompt_to_send: str = Field(
        ...,
        description=(
            "Token-optimized prompt ready to be forwarded to the target LLM tier. "
            "Includes context block if context was provided."
        ),
    )
    tier: int = Field(
        ...,
        ge=1,
        le=3,
        description="Model tier the prompt should be sent to (1 = small, 3 = frontier).",
    )
    reason: str = Field(
        ...,
        description="Primary heuristic signal that determined the tier assignment.",
    )
    original_tokens: int = Field(
        ...,
        description="Approximate word-count of the original prompt + context before optimization.",
    )
    optimized_tokens: int = Field(
        ...,
        description="Approximate word-count of the final prompt_to_send after optimization.",
    )
    tokens_saved: int = Field(
        ...,
        description="Token reduction achieved by the optimizer (original − optimized, ≥ 0).",
    )


class LLMInvokeRequest(BaseModel):
    """Request body for the /llm/invoke endpoint."""

    prompt_to_send: str = Field(
        ...,
        description="Optimized prompt produced by /route (prompt_to_send field).",
        min_length=1,
    )
    tier: int = Field(
        ...,
        ge=1,
        le=3,
        description="Numeric tier from the router (1=LOW, 2=MID, 3=HIGH).",
    )


class LLMInvokeResponse(BaseModel):
    """Response body returned by the /llm/invoke endpoint."""

    tier_number: int = Field(..., description="Numeric tier (1, 2, or 3).")
    tier_name: str = Field(..., description="Named tier: LOW | MID | HIGH.")
    model_used: str = Field(..., description="Model that produced the response.")
    models_tried: list[str] = Field(
        ...,
        description="All models attempted in order (cascade trace).",
    )
    simulated_response: str = Field(
        ...,
        description="Placeholder LLM response (real API call goes here in production).",
    )


class LLMSimulateRequest(BaseModel):
    """Request body for /llm/simulate endpoint."""

    prompt: str = Field(
        ...,
        min_length=1,
        description="Raw user prompt to route and dispatch to a simulated model.",
    )
    context: str | None = Field(
        default=None,
        description="Optional summarized conversation context used only for tier scoring.",
    )


class LLMSimulateResponse(BaseModel):
    """Response body returned by /llm/simulate endpoint."""

    tier_number: int = Field(..., description="Resolved numeric tier (1, 2, or 3).")
    tier_name: str = Field(..., description="Resolved named tier: LOW | MID | HIGH.")
    tier_reason: str = Field(..., description="Primary router reason for the tier decision.")
    model_used: str = Field(..., description="Model selected in the simulated cascade.")
    models_tried: list[str] = Field(..., description="Models attempted in order.")
    prompt_sent: str = Field(..., description="Exact prompt sent to the dispatcher.")
    simulated_response: str = Field(..., description="Simulated model response text.")


class QueryRequest(BaseModel):
    prompt: str = Field(..., min_length=1, description="Prompt to check in semantic cache.")
    user_id: str = Field(..., min_length=1, description="User identifier for personal cache lookup.")

class QueryResponse(BaseModel):
    cache_hit: bool = Field(..., description="True when a semantic cache hit is found.")
    response: str | None = Field(default=None, description="Cached response when cache_hit is true.")
    cache_layer: str = Field(..., description="Hit layer: global, personal, or miss.")
    classified: str = Field(..., description="Prompt classification used by cache: PERSONAL or GENERIC.")
    score: float | None = Field(default=None, description="Similarity score for cache hits.")


class CacheStoreRequest(BaseModel):
    prompt: str = Field(..., min_length=1, description="Original user prompt used as cache key.")
    user_id: str = Field(..., min_length=1, description="User identifier for personal cache routing.")
    response: str = Field(..., min_length=1, description="Final model response to store in cache.")
    classified: str | None = Field(
        default=None,
        description="Optional classification override: PERSONAL or GENERIC.",
    )


class CacheStoreResponse(BaseModel):
    status: str = Field(..., description="Operation status.")
    message: str = Field(..., description="Human-readable operation message.")
    stored_layer: str = Field(..., description="Storage layer used: global or personal.")

class CacheStatsResponse(BaseModel):
    global_entries: int = Field(..., description="Total entries in global cache.")
    user_stores: dict[str, int] = Field(..., description="Per-user cache entry counts.")