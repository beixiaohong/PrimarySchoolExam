"""FastAPI 应用入口"""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from .database import init_db
from .migrations.runner import run_migrations
from .routers import words, math, exam, phrases, vocab, classical, grammar, study, user, tasks, ai, mood, rewards, challenge, teach, goals, qa, parent, appeal, pet, tree, badges, cards, dictation, focus, ai_quiz, assistant, diamond
from .services.init_data import ensure_initial_data

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时初始化：建表 → 执行迁移脚本 → 基础种子数据"""
    init_db()
    run_migrations()
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
app.include_router(user.router, prefix="/api/user", tags=["用户系统"])
app.include_router(tasks.router, prefix="/api/tasks", tags=["每日任务"])
app.include_router(ai.router, prefix="/api/ai", tags=["AI 能力"])
app.include_router(mood.router, prefix="/api/mood", tags=["心情打卡"])
app.include_router(rewards.router, prefix="/api/rewards", tags=["奖励闭环"])
app.include_router(challenge.router, prefix="/api/challenge", tags=["限时挑战赛"])
app.include_router(teach.router, prefix="/api/teach", tags=["小老师模式"])
app.include_router(goals.router, prefix="/api/goals", tags=["目标倒计时"])
app.include_router(qa.router, prefix="/api/qa", tags=["十万个为什么"])
app.include_router(parent.router, prefix="/api/parent", tags=["家长功能"])
app.include_router(appeal.router, prefix="/api/appeal", tags=["申诉复核"])
app.include_router(pet.router, prefix="/api/pet", tags=["金币宠物"])
app.include_router(tree.router, prefix="/api/tree", tags=["成长树"])
app.include_router(badges.router, prefix="/api/badges", tags=["成就徽章"])
app.include_router(cards.router, prefix="/api/cards", tags=["知识卡图鉴"])
app.include_router(dictation.router, prefix="/api/dictation", tags=["听写磨耳朵"])
app.include_router(focus.router, prefix="/api/focus", tags=["番茄专注钟"])
app.include_router(ai_quiz.router, prefix="/api/ai-quiz", tags=["AI 趣味出题"])
app.include_router(assistant.router, prefix="/api/assistant", tags=["AI 学习助手"])
app.include_router(diamond.router, prefix="/api", tags=["钻石系统"])

# 前端静态资源（样式、脚本）
app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR / "static")), name="static")

# 静态资源（图片、音频）
app.mount("/output", StaticFiles(directory=str(OUTPUT_DIR)), name="output")


@app.get("/", tags=["系统"], include_in_schema=False)
def index():
    """前端首页"""
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/health", tags=["系统"])
def health():
    return {"status": "ok"}
