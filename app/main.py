"""FastAPI 应用入口（应用核心与配置）

职责：构建 FastAPI 实例、注册全部业务路由（/api/*）、同源托管前端静态资源、提供健康检查。
启动流程由 lifespan 控制：建表 → 执行迁移脚本 → 导入种子数据（见 init_db/run_migrations/ensure_initial_data）。
前端仅托管 web/dist（Vite 构建产物，需先 `cd web && npm run build`）；本项目已移除旧版 frontend/ 与管理后台 frontend-admin/。
前端由本应用同源托管，故未启用 CORSMiddleware；若前后端分离部署需跨域，请在此自行添加。
"""
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from .database import init_db
from .config import ENABLE_DOCS
from .migrations.runner import run_migrations
from .routers import words, math, exam, phrases, vocab, classical, grammar, study, search, sync, reading, user, tasks, ai, mood, rewards, challenge, teach, goals, qa, parent, appeal, pet, tree, badges, cards, dictation, focus, ai_quiz, assistant, diamond, auth, weather, admin, grading, ledger, im, admin_panel, announcement, textbook, courses, knowledge, learning_goals
from .routers.auth import require_self
from .routers.quiet_hours import check_quiet_hours
from .services.init_data import ensure_initial_data
from .logging_setup import apply_logging

# 应用导入即配置日志：按天+大小滚动，输出到 log/（控制台 + 文件双写）
apply_logging()

# P5 工程化前端构建产物（Vite build 输出，唯一托管的前端）
WEB_DIST_DIR = Path(__file__).resolve().parent.parent / "web" / "dist"
# 定义输出目录路径（用于存储生成的试卷等文件）
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output"
# 确保输出目录存在
OUTPUT_DIR.mkdir(exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时初始化：建表 → 执行迁移脚本 → 基础种子数据"""
    init_db()
    run_migrations()
    ensure_initial_data()
    logging.getLogger("app").info("应用启动完成（lifespan 初始化结束）")
    yield


app = FastAPI(
    title="小学试卷生成系统",
    description="小学数学/英语试卷自动生成 API，支持题型管理、难度配置、在线做题、错题本",
    version="1.0.0",
    lifespan=lifespan,
    # 生产环境默认关闭 Swagger / ReDoc / OpenAPI 文档（ENABLE_DOCS=true 才开启）
    docs_url="/docs" if ENABLE_DOCS else None,
    redoc_url="/redoc" if ENABLE_DOCS else None,
    openapi_url="/openapi.json" if ENABLE_DOCS else None,
)

# 业务路由统一鉴权：除登录入口 /api/auth 与管理员 /api/admin 外，全部要求登录会话 token。
# 严格账号绑定：require_self 在登录校验基础上，强制请求中的 user_id == 当前登录账号，
# 禁止用他人 user_id 操作/查他人数据（家长代管是同一账号 + 解锁密码，不受影响）。
user_auth_deps = [Depends(require_self)]

# 路由注册：业务逻辑模块挂载
# 业务路由统一要求登录会话（Bearer token）；/api/auth 与 /api/admin 例外
# （auth 自身是登录入口；admin 使用独立的 _require_admin 管理员鉴权）
app.include_router(words.router, prefix="/api/words", tags=["英语单词"], dependencies=user_auth_deps)
app.include_router(phrases.router, prefix="/api/english", tags=["英语词组与句子"], dependencies=user_auth_deps)
app.include_router(math.router, prefix="/api/math", tags=["数学题目"], dependencies=[*user_auth_deps, Depends(check_quiet_hours)])
app.include_router(exam.router, prefix="/api/exam", tags=["试卷生成"], dependencies=[*user_auth_deps, Depends(check_quiet_hours)])
app.include_router(vocab.router, prefix="/api/vocab", tags=["背单词"], dependencies=[*user_auth_deps, Depends(check_quiet_hours)])
app.include_router(classical.router, prefix="/api/classical", tags=["古诗文背诵"], dependencies=[*user_auth_deps, Depends(check_quiet_hours)])
app.include_router(grammar.router, prefix="/api/grammar", tags=["英语语法"], dependencies=[*user_auth_deps, Depends(check_quiet_hours)])
app.include_router(study.router, prefix="/api/study", tags=["学习错题与今日任务"], dependencies=[*user_auth_deps, Depends(check_quiet_hours)])
app.include_router(knowledge.router, prefix="/api/knowledge", tags=["知识点互动学习"], dependencies=user_auth_deps)
app.include_router(search.router, prefix="/api/search", tags=["搜题智能解答"], dependencies=user_auth_deps)
app.include_router(sync.router, prefix="/api/sync", tags=["同步学"], dependencies=user_auth_deps)
app.include_router(reading.router, prefix="/api/reading", tags=["阅读理解专项"], dependencies=user_auth_deps)
app.include_router(weather.router, prefix="/api/weather", tags=["天气"], dependencies=user_auth_deps)
app.include_router(admin.router, prefix="/api/admin", tags=["管理后台"])
app.include_router(user.router, prefix="/api/user", tags=["用户系统"], dependencies=user_auth_deps)
app.include_router(auth.router, prefix="/api/auth", tags=["用户认证"])
app.include_router(tasks.router, prefix="/api/tasks", tags=["每日任务"], dependencies=user_auth_deps)
app.include_router(ai.router, prefix="/api/ai", tags=["AI 能力"], dependencies=user_auth_deps)
app.include_router(grading.router, prefix="/api/ai", tags=["AI 主观题判分"], dependencies=user_auth_deps)
app.include_router(mood.router, prefix="/api/mood", tags=["心情打卡"], dependencies=user_auth_deps)
app.include_router(rewards.router, prefix="/api/rewards", tags=["奖励闭环"], dependencies=user_auth_deps)
app.include_router(challenge.router, prefix="/api/challenge", tags=["限时挑战赛"], dependencies=[*user_auth_deps, Depends(check_quiet_hours)])
app.include_router(teach.router, prefix="/api/teach", tags=["小老师模式"], dependencies=user_auth_deps)
app.include_router(goals.router, prefix="/api/goals", tags=["目标倒计时"], dependencies=user_auth_deps)
app.include_router(qa.router, prefix="/api/qa", tags=["十万个为什么"], dependencies=user_auth_deps)
app.include_router(parent.router, prefix="/api/parent", tags=["家长功能"], dependencies=user_auth_deps)
app.include_router(appeal.router, prefix="/api/appeal", tags=["申诉复核"], dependencies=user_auth_deps)
app.include_router(pet.router, prefix="/api/pet", tags=["金币宠物"], dependencies=user_auth_deps)
app.include_router(tree.router, prefix="/api/tree", tags=["成长树"], dependencies=user_auth_deps)
app.include_router(badges.router, prefix="/api/badges", tags=["成就徽章"], dependencies=user_auth_deps)
app.include_router(cards.router, prefix="/api/cards", tags=["知识卡图鉴"], dependencies=user_auth_deps)
app.include_router(dictation.router, prefix="/api/dictation", tags=["听写磨耳朵"], dependencies=[*user_auth_deps, Depends(check_quiet_hours)])
app.include_router(focus.router, prefix="/api/focus", tags=["番茄专注钟"], dependencies=user_auth_deps)
app.include_router(ai_quiz.router, prefix="/api/ai-quiz", tags=["AI 趣味出题"], dependencies=[*user_auth_deps, Depends(check_quiet_hours)])
app.include_router(assistant.router, prefix="/api/assistant", tags=["AI 学习助手"], dependencies=user_auth_deps)
app.include_router(diamond.router, prefix="/api", tags=["钻石系统"])
app.include_router(tasks.confirm_router, prefix="/api/task-confirm", tags=["完成确认"], dependencies=user_auth_deps)
# 账本(ledger)与即时通讯(im)：路由内部已用 require_user 鉴权，不挂全局 user_auth_deps
app.include_router(ledger.router, prefix="/api/ledger", tags=["个人账本"])
app.include_router(im.router, prefix="/api/im", tags=["即时通讯"])
# 后台扩展功能（数据看板/账本·IM 管理/公告）：内部用 _require_admin 鉴权
app.include_router(admin_panel.router, prefix="/api/admin", tags=["管理后台-扩展"])
# 学生端公告/站内信：内部用 require_user 鉴权
app.include_router(announcement.router, prefix="/api/announcements", tags=["系统公告"])
app.include_router(textbook.router, prefix="/api/textbook", tags=["教材版本"], dependencies=user_auth_deps)
app.include_router(courses.router, prefix="/api/courses", tags=["网课"], dependencies=user_auth_deps)
# 学习目标管理台（有终点/有总量）：路由内部已用 require_self 鉴权，不挂全局 user_auth_deps 以免重复校验
app.include_router(learning_goals.router, prefix="/api/learning-goals", tags=["学习目标管理台"])

# 前端静态资源：仅托管 P5 构建产物 web/dist（含 hash 资源）。
# 注意：web/dist 需先 `cd web && npm run build` 生成；缺失则前端不可用（接口仍正常）。
if WEB_DIST_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(WEB_DIST_DIR / "assets")), name="web-assets")
else:
    logging.getLogger("app.main").warning(
        "web/dist 不存在，前端未托管。请先 `cd web && npm run build` 生成构建产物。"
    )

# 充值 / 客服二维码等静态图：构建产物 web/dist/qr（由 web/public/qr 拷贝而来）。
# 仅当 dist/qr 存在时才挂载，避免目录缺失导致启动失败。
QR_DIR = WEB_DIST_DIR / "qr"
if QR_DIR.exists():
    app.mount("/qr", StaticFiles(directory=str(QR_DIR)), name="qr")

# 管理后台静态资源：独立 Vite 工程构建产物 admin/dist，由后端托管在 /admin。
# 前端 Vue Router 使用 hash 模式，因此只需托管 /admin（index.html）与 /admin/assets（静态资源），
# 客户端路由形如 /admin#/users，无需服务端 SPA 回退。
ADMIN_DIST_DIR = Path(__file__).resolve().parent.parent / "admin" / "dist"
ADMIN_INDEX = ADMIN_DIST_DIR / "index.html"

# 静态资源仅在构建产物存在时挂载，避免目录缺失导致启动失败。
if ADMIN_DIST_DIR.exists() and (ADMIN_DIST_DIR / "assets").exists():
    app.mount("/admin/assets", StaticFiles(directory=str(ADMIN_DIST_DIR / "assets")),
              name="admin-assets")


@app.get("/admin", include_in_schema=False)
@app.get("/admin/", include_in_schema=False)
def admin_index():
    """管理后台首页：返回 admin/dist/index.html。

    无论 admin/dist 是否已构建，/admin 都返回可读的响应（而非 FastAPI 默认 404），
    避免「构建缺失却只报 Not Found」的困惑。
    """
    if ADMIN_INDEX.exists():
        return FileResponse(ADMIN_INDEX)
    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=503,
        content={
            "detail": "管理后台未构建：请先在服务器执行 `cd admin && npm ci && npm run build` "
                      "生成 admin/dist，然后重启应用。",
        },
    )

# 静态资源（图片、音频）
app.mount("/output", StaticFiles(directory=str(OUTPUT_DIR)), name="output")


@app.get("/", tags=["系统"], include_in_schema=False)
def index():
    """前端首页：返回 Vite 构建产物 web/dist/index.html。

    若 web/dist 未构建（缺失 index.html），返回 404 并提示先执行 `npm run build`，
    避免回退到已移除的旧版前端。
    """
    index_file = WEB_DIST_DIR / "index.html"
    if index_file.exists():
        return FileResponse(
            index_file,
            headers={
                # 禁止缓存 index.html：确保浏览器始终拿到最新构建的 HTML
                # （HTML 内引用的 /assets/index-<hash>.js 本身有 content hash，可安全缓存）
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
            },
        )
    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=404,
        content={"detail": "前端未构建：请先执行 `cd web && npm run build` 生成 web/dist。"},
    )


@app.get("/health", tags=["系统"])
def health():
    """健康检查接口"""
    return {"status": "ok"}