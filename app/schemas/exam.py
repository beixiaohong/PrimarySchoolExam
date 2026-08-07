"""试卷生成相关 Schema"""
from typing import Optional, List
from pydantic import BaseModel, Field


class ExamCreateRequest(BaseModel):
    """试卷生成请求（不绑定用户，试卷为公共资源）"""
    subject: str = Field(..., description="学科：数学/英语")
    title: Optional[str] = Field(None, description="试卷标题，不填则自动生成")
    grade: int = Field(6, ge=1, le=9)
    difficulty: str = Field("综合", description="基础/提高/拔高/综合")
    user_id: Optional[str] = Field(None, description="请求者用户名（家长设置的每科最少题数将强制下限）")

    # 数学专用
    math_count: int = Field(30, ge=1, le=200, description="数学题数量")
    math_categories: Optional[List[str]] = Field(None, description="数学大类筛选")

    # 英语/语文专用
    english_count: int = Field(50, ge=1, le=200, description="英语/语文总题数（自动均分到各题型）")
    english_word_count: int = Field(50, ge=1, le=200, description="英语单词题数量(兼容旧接口)")
    english_count_per_type: int = Field(10, ge=1, le=30, description="每种英语题型数量(兼容旧接口)")
    english_book_ids: Optional[List[int]] = Field(None, description="词库ID筛选")
    english_types: Optional[List[str]] = Field(
        None, description="英语题型：word_translation/phrase_translation/sentence_translation/phonetics/grammar_choice/situational/unscramble_sentence/cloze/dictation/choice"
    )


class ExamOut(BaseModel):
    """试卷记录输出"""
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
    """单道题目输出"""
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
    image_path: str = ""
    audio_path: str = ""
    difficulty: int

    class Config:
        from_attributes = True


class WrongRecordOut(BaseModel):
    """错题记录输出（含题目详情）"""
    id: int
    user_id: str
    question_id: int
    is_mastered: bool
    is_unanswered: bool = False
    practice_count: int
    cause: str = ""  # 错因自评：careless/concept/method/reading
    wrong_at: Optional[str] = None
    mastered_at: Optional[str] = None
    # 用户作答（从最近一次 AttemptAnswer 取）
    user_answer: str = ""
    # 题目信息（展开）
    exam_id: int = 0
    seq: int = 0
    subject: str = ""
    category: str = ""
    type_code: str = ""
    type_name: str = ""
    question: str = ""
    answer: str = ""
    options_json: str = ""
    difficulty: int = 1


class MarkWrongRequest(BaseModel):
    """标记/取消错题请求

    user_id: 哪个用户的错题本
    通过 question_ids（数据库主键）或 seqs（试卷内序号）定位题目，二选一。
    """
    user_id: str = Field(..., max_length=64, description="用户标识")
    question_ids: Optional[List[int]] = Field(None, description="题目数据库ID列表")
    seqs: Optional[List[int]] = Field(None, description="试卷内序号列表")


class WrongPracticeRequest(BaseModel):
    """错题专项练习请求

    从指定用户的错题本中抽取题目生成练习卷。
    已标记为"已掌握"的题目不会被抽取。
    """
    user_id: str = Field(..., max_length=64, description="用户标识")
    subject: Optional[str] = Field(None, description="学科筛选：数学/英语，不填则混合")
    type_code: Optional[str] = Field(None, description="题型代码筛选（如 calc_int_basic）")
    count: int = Field(20, ge=5, le=100, description="练习题数量")
    include_answer: bool = Field(True, description="是否附带参考答案")
