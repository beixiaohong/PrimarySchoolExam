"""英语单词相关 Schema"""
from typing import Optional, List
from pydantic import BaseModel, Field


class WordCreate(BaseModel):
    word: str = Field(..., max_length=100, description="英文单词")
    phonetic: str = Field("", max_length=100, description="音标")
    pos: str = Field("", max_length=20, description="词性")
    meaning: str = Field(..., max_length=200, description="中文释义")
    unit: str = Field("", max_length=50, description="单元")
    difficulty: int = Field(1, ge=1, le=5)
    tags: str = Field("", description="标签，逗号分隔")


class WordUpdate(BaseModel):
    word: Optional[str] = None
    phonetic: Optional[str] = None
    pos: Optional[str] = None
    meaning: Optional[str] = None
    unit: Optional[str] = None
    difficulty: Optional[int] = Field(None, ge=1, le=5)
    tags: Optional[str] = None


class WordOut(BaseModel):
    id: int
    book_id: int
    word: str
    phonetic: str
    pos: str
    meaning: str
    unit: str
    difficulty: int
    tags: str

    class Config:
        from_attributes = True


class WordBookOut(BaseModel):
    id: int
    name: str
    grade: int
    semester: str
    publisher: str
    word_count: int

    class Config:
        from_attributes = True


class WordImportResult(BaseModel):
    total: int = Field(description="总行数")
    imported: int = Field(description="成功导入数")
    skipped: int = Field(description="跳过（重复）数")
    errors: List[str] = Field(default_factory=list, description="错误信息")


class WordQuery(BaseModel):
    grade: Optional[int] = None
    book_id: Optional[int] = None
    keyword: Optional[str] = None
    difficulty: Optional[int] = None
    page: int = 1
    page_size: int = 50
