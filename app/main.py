"""FastAPI 应用入口"""
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .database import init_db
from .routers import words, math, exam
from .services.init_data import ensure_initial_data


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时初始化数据库和种子数据"""
    init_db()
    ensure_initial_data()
    yield


app = FastAPI(
    title="小学试卷生成系统",
    description="小学数学/英语试卷自动生成 API，支持题型管理、难度配置、单词导入",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(words.router, prefix="/api/words", tags=["英语单词"])
app.include_router(math.router, prefix="/api/math", tags=["数学题目"])
app.include_router(exam.router, prefix="/api/exam", tags=["试卷生成"])


@app.get("/", tags=["系统"])
def root():
    return {"message": "小学试卷生成系统 API", "docs": "/docs"}


@app.get("/health", tags=["系统"])
def health():
    return {"status": "ok"}
