from beanie import Document
from typing import Union, List

class Configuration(Document):
    field: str
    value: Union[str, List[str]]

    class Settings:
        name = "configuration"