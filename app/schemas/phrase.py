"""词组和句子 Schema"""
from typing import Optional
from pydantic import BaseModel, Field


class PhraseCreate(BaseModel):
    """新增词组请求体（写入契约）"""
    grade: int = Field(..., ge=1, le=6)  # 年级 1~6
    phrase: str = Field(..., min_length=1)  # 必填：词组英文
    meaning: str = Field(..., min_length=1)  # 必填：中文释义
    type: str = Field("动词词组")  # 词组类型，默认“动词词组”


class PhraseOut(BaseModel):
    """词组响应契约"""
    id: int  # 主键
    grade: int  # 年级
    phrase: str  # 词组英文
    meaning: str  # 中文释义
    type: str  # 词组类型

    class Config:
        from_attributes = True


class SentenceCreate(BaseModel):
    """新增句子请求体（写入契约）"""
    grade: int = Field(..., ge=1, le=6)  # 年级 1~6
    sentence_en: str = Field(..., min_length=1)  # 必填：英文句子
    sentence_cn: str = Field(..., min_length=1)  # 必填：中文翻译
    type: str = Field("")  # 句子类型（可空）
    grammar_point: str = Field("")  # 涉及的语法点（可空）


class SentenceOut(BaseModel):
    """句子响应契约"""
    id: int  # 主键
    grade: int  # 年级
    sentence_en: str  # 英文句子
    sentence_cn: str  # 中文翻译
    type: str  # 句子类型
    grammar_point: str  # 语法点

    class Config:
        from_attributes = True
