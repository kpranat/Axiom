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
