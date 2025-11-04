from pydantic import BaseModel, Field, model_validator
from typing import List, Optional

from models.presenter import ScheduleSlot


class ScheduleInput(BaseModel):
    day: Optional[str] = Field(default=None, description="Single day (full name or 3-letter abbr)")
    days: Optional[List[str]] = Field(default=None, description="Multiple days (full names or 3-letter abbrs)")
    start: str = Field(..., description="Start time in 24h HH:MM")
    end: str = Field(..., description="End time in 24h HH:MM")

    @model_validator(mode="after")
    def _one_of_day_days(self):
        if not self.day and not self.days:
            raise ValueError("Each schedule item must include 'day' or 'days'")
        return self


class CreatePresenterRequest(BaseModel):
    name: str = Field(..., min_length=1)
    voice_id: str = Field(..., min_length=1)
    model_id: Optional[str] = None
    voice_model: Optional[str] = Field(default=None, description="Alias of model_id")
    roles: List[str] = Field(default_factory=list)
    schedules: List[ScheduleInput] = Field(default_factory=list)


class UpdatePresenterRequest(BaseModel):
    name: Optional[str] = None
    voice_id: Optional[str] = None
    model_id: Optional[str] = None
    voice_model: Optional[str] = None
    roles: Optional[List[str]] = None
    schedules: Optional[List[ScheduleInput]] = None
