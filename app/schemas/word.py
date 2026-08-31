"""英语单词相关 Schema"""
from typing import Optional, List
from pydantic import BaseModel, Field, ConfigDict


class WordCreate(BaseModel):
    """新增单词请求体（写入契约）：创建一条单词记录所需字段"""
    word: str = Field(..., max_length=100, description="英文单词")  # 必填：单词拼写
    phonetic: str = Field("", max_length=100, description="音标")  # 可选：音标
    pos: str = Field("", max_length=20, description="词性")  # 可选：词性缩写（n./v. 等）
    meaning: str = Field(..., max_length=200, description="中文释义")  # 必填：中文释义
    unit: str = Field("", max_length=50, description="单元")  # 可选：所属单元
    difficulty: int = Field(1, ge=1, le=5)  # 难度档 1~5（1 最简单，5 最难）
    tags: str = Field("", description="标签，逗号分隔")  # 可选：逗号分隔的标签


class WordUpdate(BaseModel):
    """单词更新请求体（部分更新）：所有字段均可选，仅传需要修改的字段"""
    word: Optional[str] = None  # 单词拼写（可选改）
    phonetic: Optional[str] = None  # 音标（可选改）
    pos: Optional[str] = None  # 词性（可选改）
    meaning: Optional[str] = None  # 中文释义（可选改）
    unit: Optional[str] = None  # 单元（可选改）
    difficulty: Optional[int] = Field(None, ge=1, le=5)  # 难度档（可选改，1~5）
    tags: Optional[str] = None  # 标签（可选改）


class WordOut(BaseModel):
    """单词响应契约：返回给前端的单词完整信息（读自 ORM 对象）"""
    id: int  # 主键
    book_id: int  # 所属词书 ID
    word: str  # 单词拼写
    phonetic: str  # 音标
    pos: str  # 词性
    meaning: str  # 中文释义
    unit: str  # 单元
    difficulty: int  # 难度档 1~5
    tags: str  # 标签

    model_config = ConfigDict(from_attributes=True)  # 允许从 ORM 实例直接构造


class WordBookOut(BaseModel):
    """词书响应契约：词书元信息及单词总数"""
    id: int  # 词书主键
    name: str  # 词书名
    grade: int  # 适用年级
    semester: str  # 学期（上/下）
    publisher: str  # 出版社
    word_count: int  # 该词书单词总数

    model_config = ConfigDict(from_attributes=True)


class WordImportResult(BaseModel):
    """批量导入单词结果契约：汇报导入统计与错误"""
    total: int = Field(description="总行数")  # 文件总行数
    imported: int = Field(description="成功导入数")  # 实际入库条数
    skipped: int = Field(description="跳过（重复）数")  # 因重复跳过
    errors: List[str] = Field(default_factory=list, description="错误信息")  # 逐行错误原因


class WordQuery(BaseModel):
    """单词列表查询参数（分页 + 筛选契约）"""
    grade: Optional[int] = None  # 按年级筛选
    book_id: Optional[int] = None  # 按词书筛选
    keyword: Optional[str] = None  # 关键词（单词/释义模糊匹配）
    difficulty: Optional[int] = None  # 按难度档筛选
    page: int = 1  # 页码，从 1 起
    page_size: int = 50  # 每页条数
