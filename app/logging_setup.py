"""日志配置：按天滚动 + 单日文件过大拆分，输出到 log/ 文件夹。

设计要点
--------
- 每天一个基础文件：log/YYYY-MM-DD.log
- 当天文件超过 LOG_MAX_BYTES（默认 20MB）再拆分：log/YYYY-MM-DD.part2.log、.part3.log …
- 可选保留天数 LOG_KEEP_DAYS（默认 30），处理器初始化时清理过期文件。
- 滚动逻辑由 DailySizeRotatingHandler 实现（标准库 logging.FileHandler 子类，无第三方依赖）。

使用方式
--------
1) 应用侧（app/main.py 在导入时调用，确保无论以何种方式启动都能落文件）：
       from .logging_setup import apply_logging
       apply_logging()
2) 启动器侧（让 uvicorn 自身的访问/错误日志也落文件）：
       uvicorn.run("app.main:app", log_config=build_log_config())

环境变量
--------
- LOG_DIR：日志目录，默认 <项目根>/log
- LOG_MAX_BYTES：单文件大小上限（字节），默认 20971520（20MB），<=0 表示不按大小拆分
- LOG_KEEP_DAYS：保留天数，默认 30，<=0 表示永久保留
"""
from __future__ import annotations

import logging
import logging.config
import os
import time
from datetime import datetime
from pathlib import Path

# ── 可配置项（环境变量）──
LOG_DIR = os.environ.get("LOG_DIR", str(Path(__file__).resolve().parent.parent / "log"))
try:
    LOG_MAX_BYTES = int(os.environ.get("LOG_MAX_BYTES", "20971520"))  # 默认 20MB
except ValueError:
    LOG_MAX_BYTES = 20 * 1024 * 1024
try:
    LOG_KEEP_DAYS = int(os.environ.get("LOG_KEEP_DAYS", "30"))
except ValueError:
    LOG_KEEP_DAYS = 30

_DATE_FMT = "%Y-%m-%d %H:%M:%S"


class DailySizeRotatingHandler(logging.FileHandler):
    """日志按天滚动；同一天文件超过 max_bytes 再按 part 序号拆分。

    文件命名：log/YYYY-MM-DD.log, log/YYYY-MM-DD.part2.log, log/YYYY-MM-DD.part3.log …
    """

    def __init__(self, log_dir: str = LOG_DIR, max_bytes: int = LOG_MAX_BYTES,
                 keep_days: int = LOG_KEEP_DAYS, encoding: str = "utf-8", delay: bool = False):
        self.log_dir = log_dir
        self.max_bytes = max_bytes
        self.keep_days = keep_days
        self.encoding = encoding
        self._date: str | None = None   # 当前文件对应的日期字符串
        self._part: int = 0             # 当天份号（>=1）
        os.makedirs(self.log_dir, exist_ok=True)
        self._cleanup_old()
        super().__init__(self._next_path(reset_date=True), encoding=encoding, delay=delay)

    # ── 路径计算 ──
    def _today(self) -> str:
        return datetime.now().strftime("%Y-%m-%d")

    def _next_path(self, reset_date: bool = False) -> str:
        today = self._today()
        if reset_date or today != self._date:
            self._date = today
            self._part = 1
        name = f"{today}.log" if self._part <= 1 else f"{today}.part{self._part}.log"
        return os.path.join(self.log_dir, name)

    # ── 滚动判断 ──
    def shouldRollover(self, record: logging.LogRecord) -> bool:
        # 跨天 → 滚动
        today = self._today()
        if today != self._date:
            return True
        # 不按大小拆分
        if self.max_bytes <= 0:
            return False
        if self.stream is None:
            return False
        try:
            self.stream.seek(0, 2)
            projected = self.stream.tell() + len(
                self.format(record).encode(self.encoding, "replace")
            )
            return projected >= self.max_bytes
        except Exception:
            return False

    def doRollover(self, record: logging.LogRecord):
        today = self._today()
        if today != self._date:
            # 跨天：重置为当天第 1 份
            self._part = 0
        else:
            # 当天过大：份号 +1
            self._part += 1
        if self.stream:
            try:
                self.stream.close()
            except Exception:
                pass
        self.baseFilename = os.path.abspath(self._next_path())
        self.stream = self._open()

    def emit(self, record: logging.LogRecord):
        try:
            if self.shouldRollover(record):
                self.doRollover(record)
        except Exception:
            self.handleError(record)
        super().emit(record)

    # ── 过期清理 ──
    def _cleanup_old(self):
        if self.keep_days <= 0:
            return
        try:
            cutoff = time.time() - self.keep_days * 86400
            for fn in os.listdir(self.log_dir):
                if not fn.endswith(".log"):
                    continue
                fp = os.path.join(self.log_dir, fn)
                try:
                    if os.path.getmtime(fp) < cutoff:
                        os.remove(fp)
                except OSError:
                    pass
        except OSError:
            pass


def build_log_config() -> dict:
    """构造 uvicorn 兼容的 logging 配置 dict（含按天+大小滚动文件处理器）。"""
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "()": "logging.Formatter",
                "fmt": "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                "datefmt": _DATE_FMT,
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "default",
                "level": "INFO",
                "stream": "ext://sys.stdout",
            },
            "file": {
                "()": "app.logging_setup.DailySizeRotatingHandler",
                "log_dir": LOG_DIR,
                "max_bytes": LOG_MAX_BYTES,
                "keep_days": LOG_KEEP_DAYS,
                "encoding": "utf-8",
                "formatter": "default",
                "delay": True,
            },
        },
        "loggers": {
            "uvicorn": {"handlers": ["console", "file"], "level": "INFO", "propagate": False},
            "uvicorn.error": {"handlers": ["console", "file"], "level": "INFO", "propagate": False},
            "uvicorn.access": {"handlers": ["console", "file"], "level": "INFO", "propagate": False},
            "app": {"handlers": ["console", "file"], "level": "INFO", "propagate": False},
            # SQLAlchemy 执行日志较吵，仅保留 WARNING 以上（错误/警告可见，正常查询不刷屏）
            "sqlalchemy.engine": {"handlers": ["console", "file"], "level": "WARNING", "propagate": False},
            "sqlalchemy": {"handlers": ["console", "file"], "level": "WARNING", "propagate": False},
        },
        "root": {
            "handlers": ["console", "file"],
            "level": "INFO",
        },
    }


def apply_logging():
    """应用日志配置（模块导入时调用，确保无论如何启动都能落文件）。

    失败时静默回退到 basicConfig，绝不阻断主程序启动。
    """
    try:
        logging.config.dictConfig(build_log_config())
    except Exception as e:  # pragma: no cover - 日志初始化失败不应影响主程序
        try:
            logging.basicConfig(level=logging.INFO)
        except Exception:
            pass
        logging.getLogger("app.logging_setup").warning("日志初始化失败，已回退到 basicConfig: %s", e)
