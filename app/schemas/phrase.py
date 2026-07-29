"""词组和句子 Schema"""
from typing import Optional
from pydantic import BaseModel, Field


class PhraseCreate(BaseModel):
    grade: int = Field(..., ge=1, le=6)
    phrase: str = Field(..., min_length=1)
    meaning: str = Field(..., min_length=1)
    type: str = Field("动词词组")


class PhraseOut(BaseModel):
    id: int
    grade: int
    phrase: str
    meaning: str
    type: str

    class Config:
        from_attributes = True


class SentenceCreate(BaseModel):
    grade: int = Field(..., ge=1, le=6)
    sentence_en: str = Field(..., min_length=1)
    sentence_cn: str = Field(..., min_length=1)
    type: str = Field("")
    grammar_point: str = Field("")


class SentenceOut(BaseModel):
    id: int
    grade: int
    sentence_en: str
    sentence_cn: str
    type: str
    grammar_point: str

    class Config:
        from_attributes = True
