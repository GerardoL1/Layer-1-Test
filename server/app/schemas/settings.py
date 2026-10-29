"""A person's settings, and the changes Setup and Profile can send."""

import unicodedata
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, field_validator

Units = Literal["metric", "imperial"]


class Settings(BaseModel):
    timezone: str | None
    update_time: str
    age: int | None
    training: str | None
    training_days: list[int]
    units: Units
    weight_kg: float | None = None
    name: str | None = None


class SettingsUpdate(BaseModel):
    """Only the fields sent are changed."""

    timezone: str | None = None
    update_time: str | None = None
    age: int | None = None
    training: str | None = None
    training_days: list[int] | None = None
    units: Units | None = None
    weight_kg: float | None = None
    name: str | None = None

    @field_validator("name")
    @classmethod
    def short_name(cls, v):
        # Only used to greet the person, so spaces around it go and an empty name means none.
        # Control and invisible format characters go too, except the joiner inside emoji like 👨‍👩‍👧.
        if v is not None:
            v = "".join(c for c in v if c == "\u200d" or unicodedata.category(c) not in ("Cc", "Cf"))
            v = " ".join(v.split()) or None
            # Joiners and emoji style marks don't count, so a family emoji counts as its people.
            if v is not None and len([c for c in v if c not in "\u200d\ufe0f"]) > 40:
                raise ValueError("keep the name to 40 characters or fewer")
        return v

    @field_validator("timezone")
    @classmethod
    def known_timezone(cls, v):
        if v is not None:
            try:
                ZoneInfo(v)
            except (ZoneInfoNotFoundError, ValueError):
                raise ValueError(f"unknown time zone '{v}', use a name like America/Chicago") from None
        return v

    @field_validator("update_time")
    @classmethod
    def clock_time(cls, v):
        if v is not None:
            try:
                h, m = (int(x) for x in v.split(":"))
                assert 0 <= h < 24 and 0 <= m < 60
            except (ValueError, AssertionError):
                raise ValueError("use HH:MM, for example 08:00") from None
            v = f"{h:02d}:{m:02d}"
        return v

    @field_validator("age")
    @classmethod
    def sensible_age(cls, v):
        if v is not None and not 13 <= v <= 100:
            raise ValueError("age must be between 13 and 100")
        return v

    @field_validator("weight_kg")
    @classmethod
    def sensible_weight(cls, v):
        # The app shows pounds when Units is imperial, so it converts before sending.
        if v is not None:
            if not 30 <= v <= 300:
                raise ValueError("weight must be between 30 and 300 kg (66 and 660 lb)")
            v = round(v, 1)
        return v

    @field_validator("training")
    @classmethod
    def short_text(cls, v):
        if v is not None and len(v) > 100:
            raise ValueError("keep training under 100 characters")
        return v

    @field_validator("training_days")
    @classmethod
    def weekdays(cls, v):
        if v is not None:
            if any(d not in range(7) for d in v):
                raise ValueError("training days are weekday numbers, 0 = Monday to 6 = Sunday")
            v = sorted(set(v))
        return v
