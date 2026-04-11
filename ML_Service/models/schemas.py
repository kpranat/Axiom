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
