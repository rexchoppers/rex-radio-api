from beanie import Document

class Configuration(Document):
    field: str
    value: str