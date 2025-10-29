from pydantic import BaseModel
from typing import Literal, Union, List

class UpdateConfigurationRequest(BaseModel):
    field: Literal["name", "description", "genres"]
    value: Union[str, List[str]]
