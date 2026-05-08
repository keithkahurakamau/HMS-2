from typing import List, Optional
from pydantic import BaseModel, Field


class CreateDirectConversationRequest(BaseModel):
    user_id: int


class CreateGroupConversationRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    user_ids: List[int] = Field(..., min_length=1)


class SendMessageRequest(BaseModel):
    body: str = Field(..., min_length=1, max_length=4000)


class CreateDepartmentRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(default=None, max_length=500)
    member_ids: List[int] = Field(default_factory=list)


class UpdateDepartmentRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    description: Optional[str] = Field(default=None, max_length=500)
    is_active: Optional[bool] = None


class SetDepartmentMembersRequest(BaseModel):
    member_ids: List[int]
