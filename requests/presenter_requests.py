from pydantic import BaseModel, Field
from typing import List, Optional

from models.presenter import ScheduleSlot

class CreatePresenterRequest(BaseModel):
    name: str = Field(..., min_length=1)
    voice_id: str = Field(..., min_length=1)
    model_id: str = Field(..., min_length=1)
    schedules: List[ScheduleSlot] = Field(default_factory=list)


class UpdatePresenterRequest(BaseModel):
    name: Optional[str] = None
    voice_id: Optional[str] = None
    model_id: Optional[str] = None
    schedules: Optional[List[ScheduleSlot]] = None
