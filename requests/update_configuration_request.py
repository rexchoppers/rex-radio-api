from pydantic import BaseModel
from typing import Literal

class UpdateConfigurationRequest(BaseModel):
    field: Literal["name", "description"]
    value: str
