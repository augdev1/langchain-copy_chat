import uuid
from datetime import datetime
from enum import Enum
from typing import Annotated, Any, Dict, List, Optional, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from pydantic import BaseModel, ConfigDict, Field


class FormatType(str, Enum):
    STORIES = "STORIES"
    REELS = "REELS"
    FEED = "FEED"
    WHATSAPP_LEAD = "WHATSAPP_LEAD"


class StepName(str, Enum):
    ASK_ONBOARDING = "ASK_ONBOARDING"
    CHOOSE_FORMAT = "CHOOSE_FORMAT"
    CHOOSE_SUB_INTENT = "CHOOSE_SUB_INTENT"
    AWAITING_COPY_BRIEF = "AWAITING_COPY_BRIEF"
    GENERATE_COPY = "GENERATE_COPY"
    COPY_REFINEMENT = "COPY_REFINEMENT"


class WebhookEvent(BaseModel):
    """Decoupled inbound webhook payload contract."""

    message_id: str = Field(..., description="Unique event message identifier for deduplication")
    sender_id: str = Field(..., description="Sender identifier, typically phone number (E.164)")
    message_text: str = Field(..., description="Text content sent by the user")
    timestamp: datetime = Field(..., description="Timestamp when message was generated")


class WebhookResponse(BaseModel):
    """Standardized response contract for messaging webhooks."""

    status: str = Field(..., description="'success', 'ignored', 'busy', or 'error'")
    reason: Optional[str] = Field(None, description="Reason if status is not success (e.g. duplicate_event)")
    response_text: Optional[str] = Field(None, description="Generated response message for the user")
    current_step: Optional[str] = Field(None, description="Current workflow state step")
    user_id: Optional[uuid.UUID] = Field(None, description="User UUID")
    format_type: Optional[str] = Field(None, description="Active copy format if selected")
    sub_intent: Optional[str] = Field(None, description="Sub-intent / objective if selected")


class AuditEventType(str, Enum):
    INBOUND_MESSAGE = "INBOUND_MESSAGE"
    DEDUP_BLOCKED = "DEDUP_BLOCKED"
    LOCK_CONTENTION = "LOCK_CONTENTION"
    ONBOARDING_COMPLETED = "ONBOARDING_COMPLETED"
    STATE_TRANSITION = "STATE_TRANSITION"
    SMART_INTENT_BYPASS = "SMART_INTENT_BYPASS"
    RAG_RETRIEVAL = "RAG_RETRIEVAL"
    COPY_GENERATED = "COPY_GENERATED"
    OUTBOUND_DISPATCH = "OUTBOUND_DISPATCH"
    ERROR = "ERROR"


class AuditLogResponse(BaseModel):
    """Schema for audited system events."""

    id: uuid.UUID
    event_type: str
    phone_number: str
    user_id: Optional[uuid.UUID] = None
    step_from: Optional[str] = None
    step_to: Optional[str] = None
    format_type: Optional[str] = None
    sub_intent: Optional[str] = None
    execution_time_ms: Optional[float] = None
    status: str
    payload: Optional[dict] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AgentState(TypedDict, total=False):
    """Typed StateGraph state representation for the copywriting bot."""

    user_id: uuid.UUID
    phone_number: str
    name: Optional[str]
    profession: Optional[str]
    niche: Optional[str]
    brand_handle: Optional[str]
    current_step: str
    format_type: Optional[str]
    sub_intent: Optional[str]
    last_interaction_at: datetime
    message_timestamp: datetime
    input_text: str
    response_text: Optional[str]
    messages: Annotated[List[BaseMessage], add_messages]
    error: Optional[str]
    daily_trigger_fired: Optional[bool]
    rag_context: Optional[str]
