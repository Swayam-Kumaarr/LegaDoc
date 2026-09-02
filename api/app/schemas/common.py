"""
Common Pydantic schemas across the API.
"""

from typing import Generic, List, TypeVar
from pydantic import BaseModel

T = TypeVar("T")


class ErrorResponse(BaseModel):
    detail: str


class MessageResponse(BaseModel):
    message: str


class PaginatedResponse(BaseModel, Generic[T]):
    items: List[T]
    total: int
    page: int = 1
    per_page: int = 20
