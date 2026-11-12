from __future__ import annotations

import re
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=3, max_length=32)
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)

    @model_validator(mode="after")
    def normalize_identifiers(self) -> RegisterRequest:
        username = self.username.strip().lower()
        if not re.fullmatch(r"[a-z0-9_-]{3,32}", username):
            raise ValueError("Username must use 3-32 letters, numbers, underscores, or hyphens.")
        self.username = username
        self.email = str(self.email).lower()
        return self


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=128)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    username: str
    email: EmailStr
