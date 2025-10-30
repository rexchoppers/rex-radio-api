from beanie import Document
from pydantic import BaseModel, Field, field_validator, model_validator
from typing import List, Literal
import re


days_of_week = Literal[
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
]

_TIME_RE = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")


class ScheduleSlot(BaseModel):
    day: days_of_week = Field(..., description="Day of the week in lowercase, e.g., 'monday'")
    start: str = Field(..., description="Start time in 24h HH:MM")
    end: str = Field(..., description="End time in 24h HH:MM")

    @field_validator("start", "end")
    @classmethod
    def validate_time(cls, v: str) -> str:
        if not _TIME_RE.match(v):
            raise ValueError("time must be in HH:MM 24-hour format")
        return v

    @field_validator("end")
    @classmethod
    def validate_range(cls, v: str, info):
        # Ensure end > start in lexical HH:MM since fixed width
        start = info.data.get("start")
        if start and v <= start:
            raise ValueError("end time must be later than start time")
        return v


class Presenter(Document):
    name: str
    voice_id: str
    model_id: str
    schedules: List[ScheduleSlot] = Field(default_factory=list)

    class Settings:
        name = "presenters"
