from pydantic import BaseModel


class ProcessingRun(BaseModel):
    processed: bool
    new_nights: list[str]
    message: str


class DemoUser(BaseModel):
    user_id: str
    clock_local: str


class HealthCheck(BaseModel):
    ok: bool
