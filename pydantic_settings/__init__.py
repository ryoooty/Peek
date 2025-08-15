from pydantic import BaseModel, Field

class SettingsConfigDict(dict):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

class BaseSettings(BaseModel):
    model_config: dict = {}
