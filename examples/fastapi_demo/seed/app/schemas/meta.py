from pydantic import BaseModel


class VersionResponse(BaseModel):
    name: str
    version: str

