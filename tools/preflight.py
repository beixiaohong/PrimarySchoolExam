"""部署前置自检：在**重启服务之前**验证新版本能不能真正跑起来

为什么需要它（2026-09-24 线上全站 502 事故）
-------------------------------------------
`deploy.sh` 的顺序是「装依赖 → 构建前端 → **重启服务** → 检查进程/健康」。
致命点在于**检查发生在重启之后**：一旦新版本有问题（如 requirements.txt 漏声明
httpx），systemd 已经把服务换成坏版本，`Restart=always` 让它反复崩溃重启，全站 502。
deploy.sh 虽然会报错退出，但那时站点已经挂了、旧版本的进程也没了 ——
**"部署失败" 变成了 "站点下线"**。

本脚本把检查**前移到重启之前**：全部通过才允许重启；任一项 BLOCK 就中止部署，
正在运行的旧版本不受影响，站点保持可用（只是没更新成功）。

两级 stage
----------
- `early`：装完依赖、修完属主后立刻能查的项 —— 依赖完整性 + 应用可导入 + .env 必需键。
  放在前端构建**之前**执行，避免发现问题时已白跑几分钟 npm build。
- `full`：再加上外部命令、前端产物、目录检查，放在**写 systemd/nginx 配置与重启之前**。

检查项与严重级别
----------------
BLOCK —— 会导致部署后不可服务，必须中止：
  · 依赖完整性（app/ 启动期硬导入是否都在 requirements.txt）
  · 应用可导入（`python -c "import app.main"`，终极检验）
  · .env 数据库必需键（DB_HOST/DB_USER/DB_NAME）
  · 前端 web/dist 产物缺失
WARN —— 功能降级，允许继续但必须让操作者看见：
  · ffmpeg/ffprobe（IM 语音转 MP3）、soffice（LibreOffice，试卷 .doc 解析）
  · npm/node（前端重建需要）、admin/dist 缺失
  · 可选 API Key 缺失（按功能列出影响）

实现约束
--------
**纯标准库**：即使 venv 已损坏、第三方包装不上，也必须能跑起来 —— 这正是最需要它的场景。
依赖完整性复用 `tools/dep_audit.py`（按路径加载，不 import 项目包）。

用法
----
    python tools/preflight.py                     # 本地，默认 early
    python tools/preflight.py --stage full        # 全量
    python tools/preflight.py --app-dir /home/PrimarySchoolExam \\
        --python /home/PrimarySchoolExam/venv/bin/python --app-user www-data

退出码 0 = 可以部署；1 = 有 BLOCK 项，部署应中止。
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# ── 检查项配置 ──

# 数据库必需键：缺失则服务起来也连不上库（engine 是惰性的，import 检查抓不到）
ENV_REQUIRED = {
    "DB_HOST": "数据库地址",
    "DB_USER": "数据库账号",
    "DB_NAME": "数据库名",
}
# 建议填写：缺失不阻断，但对应功能会降级
ENV_OPTIONAL = {
    "DB_PASSWORD": "数据库密码（为空则连接失败）",
    "DEEPSEEK_API_KEY": "AI 链路（出题/批改/问答/导读）—— 当前线上唯一可用链路",
    "ZHIPU_API_KEY": "AI 链路备用（智谱 GLM）",
    "RELAY_API_KEY": "AI 链路备用（Relay 中转）",
    "MAIL_ADDRESS": "邮箱验证码与通知",
    "MAIL_PASSWORD": "邮箱验证码与通知",
    "QWEATHER_API_KEY": "首页天气卡片",
    "SMS_API_KEY": "短信验证码登录",
    "XF_API_KEY": "讯飞语音相关功能",
}

# 外部命令：缺失不阻断启动，但对应功能不可用
EXTERNAL_BINS = [
    ("ffmpeg", "IM 语音消息转 MP3（后端统一转码）"),
    ("ffprobe", "语音时长探测（配合 ffmpeg）"),
    ("soffice", "LibreOffice：解析旧版 .doc 试卷（采集脚本用，非服务运行期）"),
    ("npm", "前端重建（web/admin 源码变更时 deploy.sh 需要）"),
]


class Finding:
    """一条检查结果

    刻意用普通类而非 dataclass：本脚本要能被「按路径加载」（spec_from_file_location）
    或独立运行 —— 不注册进 sys.modules 时，dataclass 解析字符串注解会抛
    `AttributeError: 'NoneType' object has no attribute '__dict__'`。
    一个「部署闸门」脚本不该有这种脆弱依赖（测试即抓到过）。
    """

    __slots__ = ("name", "level", "detail", "hint", "impact")

    def __init__(self, name: str, level: str, detail: str = "",
                 hint: str = "", impact: str = ""):
        self.name = name
        self.level = level          # "ok" | "warn" | "block"
        self.detail = detail
        self.hint = hint
        self.impact = impact

    @property
    def marker(self) -> str:
        return {"ok": "[ OK ]", "warn": "[WARN]", "block": "[BLOCK]"}[self.level]


# ── 各项检查 ──

_AUDIT_CACHE: dict = {}


def _load_audit(app_dir: Path):
    """按路径加载 tools/dep_audit.py（复用其 requirements 解析与别名表）"""
    key = str(app_dir)
    if key in _AUDIT_CACHE:
        return _AUDIT_CACHE[key]
    audit_path = app_dir / "tools" / "dep_audit.py"
    mod = None
    if audit_path.exists():
        try:
            spec = importlib.util.spec_from_file_location("dep_audit", audit_path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
        except Exception:
            mod = None
    _AUDIT_CACHE[key] = mod
    return mod


def check_dependencies(app_dir: Path, requirements: Path | None = None) -> list[Finding]:
    """应用启动期硬导入是否都在 requirements.txt 声明（复用 dep_audit）"""
    mod = _load_audit(app_dir)
    if mod is None:
        return [Finding("依赖完整性", "warn", "未找到 tools/dep_audit.py（旧版本代码？跳过）")]
    try:
        result = mod.audit([app_dir / "app"], requirements=requirements)
    except Exception as e:  # 审计脚本自身出错不应该阻断部署
        return [Finding("依赖完整性", "warn", f"审计执行异常：{type(e).__name__}: {e}")]

    if not result["errors"]:
        st = result["stats"]
        return [Finding("依赖完整性", "ok",
                        f"{st['files_scanned']} 个文件、"
                        f"{st['third_party_modules']} 个启动期第三方模块全部已声明")]
    out = []
    for e in result["errors"]:
        out.append(Finding(
            f"依赖未声明：{e['module']}", "block",
            detail="; ".join(e["files"][:3]),
            hint=f"把 {e['dist']}（含版本）加进 requirements.txt 后重新部署",
            impact="线上 venv 按清单装包，缺包会在应用导入期直接崩溃（全站 502）",
        ))
    return out


def check_import(app_dir: Path, python: str, app_user: str = "",
                 requirements: Path | None = None) -> Finding:
    """终极检验：用**服务所用的解释器**真实导入 app.main

    比静态检查更可靠 —— 任何导入期错误（缺包、语法错、配置错、日志目录不可写）都会暴露。
    以 root 部署且指定了 --app-user 时，会切到该用户执行，顺带验证文件属主/权限是否就绪
    （git pull 以 root 执行会留下 root 属主的文件，服务用户可能读不到）。
    """
    as_user = bool(app_user) and hasattr(os, "geteuid") and os.geteuid() == 0
    note = ""
    if as_user and not shutil.which("su"):
        as_user, note = False, "（系统无 su 命令，退化为以当前用户检查）"

    def _run(cmd: list[str]):
        return subprocess.run(cmd, cwd=str(app_dir), capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=120)

    direct_cmd = [python, "-c", "import app.main"]
    if as_user:
        # root 部署：切到服务用户执行（git pull 以 root 执行会留下 root 属主的文件，
        # 服务用户可能读不到 —— 借这次真实导入把权限问题一起暴露出来）
        inner = f'cd "{app_dir}" && "{python}" -c "import app.main"'
        cmd = ["su", "-s", "/bin/sh", "-c", inner, app_user]
        who = f"以服务用户 {app_user} 运行"
    else:
        # 不套 shell（Windows 无 /bin/sh），直接调解释器并指定工作目录
        cmd, who = direct_cmd, "以当前用户运行"

    try:
        r = _run(cmd)
        if as_user and r.returncode != 0 and "Traceback" not in (r.stderr or ""):
            # su 自身失败（如目标用户不可用）而非 Python 导入报错 —— 退化为直接运行，
            # 避免因环境差异误拦部署（闸门误报会让人绕开它，比漏报更糟）。
            r = _run(direct_cmd)
            who += "（su 执行失败，已退化为当前用户）"
    except FileNotFoundError as e:
        return Finding("应用可导入", "block", f"无法执行检查命令：{e}",
                       hint="确认解释器路径正确（--python 参数）")
    except subprocess.TimeoutExpired:
        return Finding("应用可导入", "block", "导入超时（>120s）",
                       hint="检查是否有导入期的网络/数据库阻塞调用")

    if r.returncode == 0:
        return Finding("应用可导入", "ok", f"python -c 'import app.main' 成功（{who}）")

    tail = ((r.stderr or "") + (r.stdout or "")).strip().splitlines()[-12:]
    err_line = next((l.strip() for l in reversed(tail) if "Error" in l or "error" in l), "")
    hint = ""
    m = re.search(r"ModuleNotFoundError: No module named '([^']+)'", r.stderr or "")
    if m:
        missing = m.group(1).split(".")[0]
        audit = _load_audit(app_dir)
        declared: set = set()
        if audit is not None:
            declared = set(audit.declared_distributions(requirements))
            alias = audit.norm(audit.ALIAS.get(missing, ""))
        else:
            alias = ""
        if audit is not None and (audit.norm(missing) in declared or (alias and alias in declared)):
            # 名称已在清单里 —— 说明清单没问题，是「没装进这个 venv」
            hint = (f"依赖 {missing} 已在 requirements.txt 声明，但该解释器里没有装 —— "
                    f"执行 `pip install -r requirements.txt`，并确认装进了服务所用的 venv")
        else:
            hint = (f"缺少依赖 {missing} —— requirements.txt 很可能漏声明了它"
                    f"（本地装了、线上没装）。补进清单后重新部署。")
    elif "Permission denied" in (r.stderr or ""):
        hint = "文件权限/属主问题：确认 deploy.sh 已完成 chown -R $APP_USER（以服务用户运行检查）"
    return Finding("应用可导入", "block", " | ".join(tail[-3:]) if tail else f"退出码 {r.returncode}",
                   hint=hint, impact="服务会启动失败并被 systemd 反复重启，全站 502")


def check_env(app_dir: Path) -> list[Finding]:
    """`.env` 关键变量检查（服务由 systemd 的 EnvironmentFile 注入）"""
    env_file = app_dir / ".env"
    if not env_file.exists():
        return [Finding(".env 文件", "block", f"未找到 {env_file}",
                        hint="参考 .env.example 创建，并至少填好 DB_* 四项",
                        impact="缺少 .env 时服务连不上数据库")]
    values = {}
    for raw in env_file.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        values[k.strip()] = v.strip().strip('"').strip("'")

    out = [Finding(".env 文件", "ok", f"{env_file.name} 存在，读取到 {len(values)} 个键")]
    for key, desc in ENV_REQUIRED.items():
        if not values.get(key):
            out.append(Finding(f".env 缺少 {key}", "block", f"（{desc}）未配置",
                               hint=f"在 .env 中补充 {key}", impact="服务连不上数据库"))
    for key, desc in ENV_OPTIONAL.items():
        if not values.get(key):
            out.append(Finding(f".env 未配置 {key}", "warn", desc,
                               hint=f"不需要该功能可忽略；需要则补充 {key}"))
    driver = (values.get("DB_DRIVER") or "mysql").lower()
    if driver != "mysql":
        out.append(Finding(".env DB_DRIVER", "warn", f"当前为 {driver}",
                           hint="本项目已 MySQL-only，非 mysql 会回退为 mysql"))
    return out


def check_external_bins() -> list[Finding]:
    """外部命令可用性（缺失通常只影响单个功能，不阻断部署）"""
    out = []
    for name, impact in EXTERNAL_BINS:
        path = shutil.which(name)
        if path:
            out.append(Finding(f"外部命令 {name}", "ok", path))
        else:
            out.append(Finding(f"外部命令 {name}", "warn", "未安装",
                               hint={"ffmpeg": "apt install ffmpeg",
                                     "ffprobe": "apt install ffmpeg",
                                     "soffice": "apt install libreoffice",
                                     "npm": "apt install nodejs npm"}.get(name, ""),
                               impact=impact))
    return out


def check_dist(app_dir: Path) -> list[Finding]:
    """前端构建产物（缺失则页面空白/后台 404，但服务本身能启动）"""
    out = []
    for sub, level, why in (("web", "block", "主站前端"), ("admin", "warn", "管理后台")):
        idx = app_dir / sub / "dist" / "index.html"
        if idx.exists():
            out.append(Finding(f"{why}产物", "ok", f"{sub}/dist/index.html"))
        else:
            out.append(Finding(f"{why}产物缺失", level, f"未找到 {sub}/dist/index.html",
                               hint=f"deploy.sh 会在源码变更时自动构建 {sub}/",
                               impact=f"{why}无法访问"))
    return out


# ── 编排与输出 ──

def run(app_dir: Path, python: str, stage: str = "early", app_user: str = "",
        requirements: Path | None = None) -> list[Finding]:
    findings: list[Finding] = []
    findings += check_dependencies(app_dir, requirements)
    findings.append(check_import(app_dir, python, app_user, requirements))
    findings += check_env(app_dir)
    if stage == "full":
        findings += check_external_bins()
        findings += check_dist(app_dir)
    return findings


def report(findings: list[Finding], stage: str) -> int:
    blocks = [f for f in findings if f.level == "block"]
    warns = [f for f in findings if f.level == "warn"]
    print("=" * 68)
    print(f"部署前置自检（stage={stage}）")
    print("=" * 68)
    for f in findings:
        if f.level == "ok":
            print(f"{f.marker} {f.name}" + (f" —— {f.detail}" if f.detail else ""))
    for f in warns + blocks:
        print(f"{f.marker} {f.name}" + (f" —— {f.detail}" if f.detail else ""))
        if f.impact:
            print(f"         影响：{f.impact}")
        if f.hint:
            print(f"         处理：{f.hint}")
    print("-" * 68)
    if blocks:
        print(f"结论：{len(blocks)} 项阻断、{len(warns)} 项警告 —— 不要重启服务，"
              f"先修掉阻断项再部署")
        return 1
    print(f"结论：可以部署（{sum(1 for f in findings if f.level == 'ok')} 项通过，"
          f"{len(warns)} 项警告）")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="部署前置自检（重启前验证新版本可运行）")
    p.add_argument("--app-dir", default=str(ROOT), help="项目根目录（默认脚本上级目录）")
    p.add_argument("--python", default=sys.executable, help="服务所用 Python 解释器路径")
    p.add_argument("--stage", choices=("early", "full"), default="early",
                   help="early=依赖+导入+env；full=再加外部命令与产物检查")
    p.add_argument("--app-user", default="", help="服务运行用户（root 部署时切到该用户做导入检查）")
    p.add_argument("--requirements", default="", help="依赖清单路径（默认 项目根/requirements.txt）")
    args = p.parse_args(argv)

    app_dir = Path(args.app_dir).resolve()
    python = args.python
    requirements = Path(args.requirements).resolve() if args.requirements else None
    # 自动探测 venv 解释器（未显式指定且默认值不是 venv 时）
    if python == sys.executable:
        for cand in (app_dir / "venv" / "bin" / "python",
                     app_dir / ".venv" / "Scripts" / "python.exe",
                     app_dir / ".venv" / "bin" / "python"):
            if cand.exists():
                python = str(cand)
                break

    return report(run(app_dir, python, args.stage, args.app_user, requirements), args.stage)


if __name__ == "__main__":
    sys.exit(main())
