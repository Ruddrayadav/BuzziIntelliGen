"""Request and safe response models used by the HTTP API."""

from pydantic import BaseModel, Field


class RegisterRequest(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=8, max_length=512)
    business_name: str = Field(min_length=1, max_length=100)


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=512)


class PublicUser(BaseModel):
    username: str
    business_name: str


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2_000)
