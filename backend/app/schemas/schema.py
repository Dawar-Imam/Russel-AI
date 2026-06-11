from pydantic import BaseModel


class DemoMessage(BaseModel):
    message: str
