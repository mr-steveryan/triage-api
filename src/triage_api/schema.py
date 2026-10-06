from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class Category(StrEnum):
    BUG = "bug"
    FEATURE = "feature"    
    BILLING = "billing"
    OTHER = "other"

class Urgency(StrEnum):
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"

class TriageRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    support_message: str = Field(min_length=1, max_length=1000)

class TriageResponse(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    category: Category
    urgency: Urgency
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = Field(min_length=1, max_length=200)