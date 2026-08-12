"""Schemas 统一导出入口：集中 re-export 各子模块的 Pydantic 模型，便于 `from app.schemas import X` 直接调用。"""
from .word import WordCreate, WordUpdate, WordOut, WordImportResult
from .problem import ProblemTypeCreate, ProblemTypeOut, MathGenRequest, MathGenResponse
from .exam import ExamCreateRequest, ExamOut

__all__ = [
    "WordCreate", "WordUpdate", "WordOut", "WordImportResult",
    "ProblemTypeCreate", "ProblemTypeOut", "MathGenRequest", "MathGenResponse",
    "ExamCreateRequest", "ExamOut",
]
