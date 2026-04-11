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
