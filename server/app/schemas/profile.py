from pydantic import BaseModel

from app.schemas.settings import Settings


class UsualRange(BaseModel):
    key: str
    label: str
    unit: str
    usual_low: float | None
    usual_high: float | None
    baseline_nights: float | None
    placeholder: bool


class Profile(BaseModel):
    user_id: str
    settings: Settings
    nights_total: int
    nights_usable: int
    first_night: str | None
    last_night: str | None
    baseline_window_nights: int
    baseline_min_nights: int
    usual_ranges: list[UsualRange]
    sources: list[str]
    last_update_local: str | None
