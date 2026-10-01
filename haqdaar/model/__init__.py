"""haqdaar/model/__init__.py

Public interface for HAQDAAR v2 Model module.
Exposes Model router, GroqModelClient, SpanGuard, and result types.
"""
from haqdaar.contracts.types import (
    Answer,
    Clarify,
    Meta,
    Repeat,
    Stamp,
    TurnResult,
    Unclear,
)
from haqdaar.model.client import GroqModelClient, ModelClientResponse
from haqdaar.model.router import Model
from haqdaar.model.span_guard import SpanGuard

__all__ = [
    "Model",
    "GroqModelClient",
    "ModelClientResponse",
    "SpanGuard",
    "Stamp",
    "Answer",
    "Clarify",
    "Repeat",
    "Meta",
    "Unclear",
    "TurnResult",
]
