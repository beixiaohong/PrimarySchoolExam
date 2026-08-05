"""FastAPI 应用入口"""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from .database import init_db
from .routers import words, math, exam, phrases, vocab, classical, grammar, study
from .services.init_data import ensure_initial_data

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时初始化数据库和种子数据"""
    init_db()
    ensure_initial_data()
    yield


app = FastAPI(
    title="小学试卷生成系统",
    description="小学数学/英语试卷自动生成 API，支持题型管理、难度配置、在线做题、错题本",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(words.router, prefix="/api/words", tags=["英语单词"])
app.include_router(phrases.router, prefix="/api/english", tags=["英语词组与句子"])
app.include_router(math.router, prefix="/api/math", tags=["数学题目"])
app.include_router(exam.router, prefix="/api/exam", tags=["试卷生成"])
app.include_router(vocab.router, prefix="/api/vocab", tags=["背单词"])
app.include_router(classical.router, prefix="/api/classical", tags=["古诗文背诵"])
app.include_router(grammar.router, prefix="/api/grammar", tags=["英语语法"])
app.include_router(study.router, prefix="/api/study", tags=["学习错题与今日任务"])

# 静态资源（图片、音频）
app.mount("/output", StaticFiles(directory=str(OUTPUT_DIR)), name="output")


@app.get("/", tags=["系统"], include_in_schema=False)
def index():
    """前端首页"""
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/health", tags=["系统"])
def health():
    return {"status": "ok"}
