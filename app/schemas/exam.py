"""试卷生成相关 Schema"""
from typing import Optional, List
from pydantic import BaseModel, Field


class ExamCreateRequest(BaseModel):
    """试卷生成请求"""
    subject: str = Field(..., description="学科：数学/英语")
    title: Optional[str] = Field(None, description="试卷标题，不填则自动生成")
    grade: int = Field(6, ge=1, le=6)
    difficulty: str = Field("综合", description="基础/提高/拔高/综合")

    # 数学专用
    math_count: int = Field(30, ge=5, le=200, description="数学题数量")
    math_categories: Optional[List[str]] = Field(None, description="数学大类筛选")

    # 英语专用
    english_word_count: int = Field(50, ge=10, le=200, description="英语单词题数量(兼容旧接口)")
    english_count_per_type: int = Field(10, ge=3, le=30, description="每种英语题型数量")
    english_book_ids: Optional[List[int]] = Field(None, description="词库ID筛选")
    english_types: Optional[List[str]] = Field(
        None, description="英语题型：word_translation/phrase_translation/sentence_translation/phonetics/grammar_choice/situational/unscramble_sentence/cloze/dictation/choice"
    )


class ExamOut(BaseModel):
    id: int
    subject: str
    title: str
    grade: int
    difficulty: str
    question_count: int
    file_path: str
    created_at: str

    class Config:
        from_attributes = True


class QuestionOut(BaseModel):
    id: int
    exam_id: int
    seq: int
    subject: str
    category: str
    type_code: str
    type_name: str
    question: str
    answer: str
    options_json: str
    difficulty: int
    is_wrong: bool
    wrong_at: Optional[str] = None

    class Config:
        from_attributes = True


class MarkWrongRequest(BaseModel):
    """标记错题请求"""
    question_ids: Optional[List[int]] = Field(None, description="题目ID列表（与seqs二选一）")
    seqs: Optional[List[int]] = Field(None, description="题目序号列表（与question_ids二选一）")


class WrongPracticeRequest(BaseModel):
    """错题专项练习请求"""
    subject: Optional[str] = Field(None, description="学科筛选：数学/英语，不填则全部")
    type_code: Optional[str] = Field(None, description="题型代码筛选")
    count: int = Field(20, ge=5, le=100, description="练习题数量")
    include_answer: bool = Field(True, description="是否包含答案")
