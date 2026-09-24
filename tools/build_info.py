"""前端构建溯源与「前后端契约」一致性检查

解决什么问题
------------
前端是编译产物（web/dist、admin/dist），后端是源码直跑 —— 两者版本可以**各自漂移**，
而漂移的症状是"用户点了没反应"，排查时又极易被误当成后端 bug：

1. **旧 dist 配新后端**：后端把 `/api/study/plan` 改名/删除，前端产物里仍写着旧路径 →
   线上 404；页面不报错、按钮静默失效。
2. **旧 dist 配新源码**：前端源码改了但 dist 没重建（`deploy.sh` 原先用 mtime 判断是否重建，
   只看 `src/`、`package.json`、`vite.config.js`，**漏掉 `index.html` / `novel.html` / `public/`**，
   还漏掉"删除文件"）→ 线上一直跑旧界面，且没有任何提示。

本脚本提供两件事：
- **构建溯源**：构建时把「源码输入指纹 + 产物引用的 API 路径」写进 `dist/.build-info.json`；
  部署时可反查「这份 dist 到底是不是当前源码构建的」，并精确列出变了的源文件。
- **契约配对**：把产物里引用的 `/api/...` 路径与后端 openapi 路由表比对，
  找出「前端在调、后端没有」的路径（= 接口改名/删除后前端没跟上）。

用法
----
    python tools/build_info.py write --dir web        # 构建后记录（deploy.sh 自动调用）
    python tools/build_info.py needs-build --dir web  # 退出码 0=需重建 / 1=无需（供 shell 判断）
    python tools/build_info.py check --dir web        # 校验新鲜度 + 前后端契约
    python tools/build_info.py show --dir web         # 查看已记录的构建信息

设计约束
--------
**纯标准库**：本脚本在部署链路上被调用（preflight 会按路径加载它），
venv 半坏时也必须能跑；同理**不使用 dataclass / `from __future__ import annotations`**
（按路径加载、未注册 sys.modules 时，字符串注解解析会抛 AttributeError —— 详见 tools/preflight.py）。

与 tools/regression_check.py 第 [5] 项的分工（两处都在查"前端 vs 后端路由"，别误当重复）
------------------------------------------------------------------------------------
- regression_check 查**源码**（`web/src/**`，严格归一化相等）→ 提交前就能发现"后端改了接口名
  但前端没跟上"，不必先构建；但要跑得早，所以规则取严（宁可少报）。
- 本脚本查**产物**（`dist/assets/*.js`）→ 打包会把 `` `/api/x/${id}` `` 压成静态字面量片段，
  源码里的结构信息没了，所以规则必须放宽（段级通配 + 前缀），否则会大量误报。
  这也是唯一能发现"线上那份 dist 与当前后端不匹配"的地方（源码扫描看不到产物）。
"""
import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

SCHEMA = 1  # build-info 结构版本；字段含义变化时递增

# 参与构建的源码输入（按工程名匹配）
# 为什么连 index.html / public 都要算：vite 会把它们原样搬进 dist，
# 改标题、改 meta、换 public 下的图片都**必须重建**，但都不会让 src/ 变新。
SOURCE_SPECS = {
    "web": (("src", "public"), ("index.html", "novel.html",
                                "package.json", "package-lock.json", "vite.config.js")),
    "admin": (("src",), ("index.html", "package.json", "package-lock.json", "vite.config.js")),
}
# 未登记的新工程：保守取 src
SOURCE_SPECS_DEFAULT = (("src",), ("index.html", "package.json", "vite.config.js"))

# 遍历源码目录时跳过的子目录（node_modules 数千文件，且不影响构建产物）
SKIP_DIRS = {"node_modules", "dist", ".vite", ".git", "__pycache__", ".cache"}

# 从产物 JS 里提取 API 路径字面量。
# 只认「引号后紧跟 /api/」—— 打包后 axios 调用形如 `"/api/study/plan"` 或 `` `/api/im/chats/${id}` ``；
# 模板串里的 `${` 不在字符集内，天然被截断成静态前缀（`/api/im/chats/`），
# 正好用前缀匹配后端路由（见 route_exists）。
API_RE = re.compile(r"""['"`](/api/[A-Za-z0-9_/\-]{0,80})""")
# 无信息量的候选：连一个业务段都没有
API_TRIVIAL = {"/api", "/api/"}


# ── 源码指纹 ──

def source_files(project: Path) -> list[Path]:
    """列出参与构建的源码输入文件（绝对路径，按相对路径排序保证可复现）"""
    dirs, files = SOURCE_SPECS.get(project.name, SOURCE_SPECS_DEFAULT)
    out: list[Path] = []
    for d in dirs:
        base = project / d
        if not base.is_dir():
            continue
        for p in base.rglob("*"):
            if p.is_file() and not any(part in SKIP_DIRS for part in p.relative_to(project).parts):
                out.append(p)
    for f in files:
        p = project / f
        if p.is_file():
            out.append(p)
    return sorted(out, key=lambda p: p.relative_to(project).as_posix())


def file_digests(project: Path) -> dict:
    """{相对路径: 内容 sha256 前 8 位} —— 逐文件摘要用于精确指出"构建后又改了哪些文件"

    直接哈希原始字节（不做换行归一），因为构建读的就是原始字节。
    """
    out = {}
    for p in source_files(project):
        h = hashlib.sha256()
        try:
            h.update(p.read_bytes())
        except OSError:
            continue  # 读到一半被删/无权限：跳过，不让部署链路上的工具抛异常
        out[p.relative_to(project).as_posix()] = h.hexdigest()[:8]
    return out


def fingerprint_of(digests: dict) -> str:
    """由逐文件摘要合成工程总指纹"""
    h = hashlib.sha256()
    for rel, d in sorted(digests.items()):
        h.update(f"{rel}:{d}\n".encode("utf-8"))
    return h.hexdigest()[:16]


def source_fingerprint(project: Path) -> tuple:
    """返回 (总指纹, 文件数, 逐文件摘要)"""
    digests = file_digests(project)
    return fingerprint_of(digests), len(digests), digests


# ── 产物扫描 ──

def scan_api_paths(dist: Path) -> list[str]:
    """扫描构建产物里引用的 API 路径字面量（去重排序）"""
    js_files: list[Path] = []
    assets = dist / "assets"
    if assets.is_dir():
        js_files = sorted(assets.glob("*.js"))
    if not js_files:  # 产物目录名被改过时的兜底
        js_files = sorted(p for p in dist.rglob("*.js") if p.is_file())
    found = set()
    for p in js_files:
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for m in API_RE.finditer(text):
            path = m.group(1)
            if path not in API_TRIVIAL:
                found.add(path)
    return sorted(found)


def dist_assets(dist: Path) -> list[str]:
    """产物文件名清单（用于判断 dist 是否被外部替换过）"""
    if not dist.is_dir():
        return []
    return sorted(p.name for p in dist.iterdir() if p.is_file())


# ── 构建信息读写 ──

def dist_dir(project: Path) -> Path:
    return project / "dist"


def build_info_path(project: Path) -> Path:
    return dist_dir(project) / ".build-info.json"


def read_build_info(project: Path) -> dict:
    """读取 build-info；不存在/损坏都返回 None（调用方按"无法校验"处理）"""
    p = build_info_path(project)
    if not p.is_file():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _git_info(project: Path) -> dict:
    """当前 git 版本（失败静默：构建场合可能没有 git 或无 .git）"""
    def run(args):
        try:
            r = subprocess.run(["git", *args], cwd=str(project), capture_output=True,
                               text=True, encoding="utf-8", errors="replace", timeout=10)
            return r.stdout.strip() if r.returncode == 0 else ""
        except (OSError, subprocess.SubprocessError):
            return ""

    sha = run(["rev-parse", "--short", "HEAD"])
    dirty = bool(run(["status", "--porcelain", "--", "."]))
    return {"git_sha": sha, "git_dirty": dirty}


def write_build_info(project: Path, note: str = "") -> dict:
    """构建完成后写入 dist/.build-info.json（无 dist 则抛 FileNotFoundError）"""
    dist = dist_dir(project)
    if not dist.is_dir():
        raise FileNotFoundError(f"未找到构建产物目录：{dist}")
    fp, count, digests = source_fingerprint(project)
    info = {
        "schema": SCHEMA,
        "project": project.name,
        "built_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "source_hash": fp,
        "source_count": count,
        "sources": digests,
        "api_paths": scan_api_paths(dist),
        "assets": dist_assets(dist),
        **_git_info(project),
    }
    if note:
        info["note"] = note
    build_info_path(project).write_text(
        json.dumps(info, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    return info


def changed_sources(project: Path, info: dict) -> list[str]:
    """与构建时相比发生了变化的源文件（新增/修改/删除都算）"""
    old = info.get("sources") or {}
    _, _, now = source_fingerprint(project)
    out = []
    for rel in sorted(set(old) | set(now)):
        if old.get(rel) != now.get(rel):
            tag = "新增" if rel not in old else ("删除" if rel not in now else "修改")
            out.append(f"{tag} {rel}")
    return out


def needs_build(project: Path) -> tuple:
    """是否需要重新构建 → (bool, 原因)

    判据是**内容指纹**而非 mtime：mtime 判据会漏掉 `index.html`/`novel.html`/`public/`
    的改动与"删除了源文件"，还会被 `git pull` 的文件时间顺序误导 —— 漏判的后果是
    线上静默沿用旧界面。没有 build-info（首次启用/旧产物）一律视为需要构建，
    这样机制上线后第一次部署会自然重建一次，之后即收敛。
    """
    dist = dist_dir(project)
    if not (dist / "index.html").is_file():
        return True, "尚无构建产物"
    info = read_build_info(project)
    if info is None:
        return True, "缺少构建信息（无法确认 dist 是否对应当前源码）"
    if info.get("schema") != SCHEMA:
        return True, f"构建信息版本不符（{info.get('schema')} != {SCHEMA}）"
    fp, count, _ = source_fingerprint(project)
    if fp != info.get("source_hash"):
        changed = changed_sources(project, info)
        head = "、".join(changed[:3])
        more = f" 等 {len(changed)} 个" if len(changed) > 3 else ""
        return True, f"源码已变更（{head}{more}）"
    return False, f"源码未变（{count} 个文件，指纹 {fp}）"


# ── 前后端契约比对 ──

def _split(path: str) -> list:
    return [s for s in path.strip("/").split("/") if s]


def route_exists(front_path: str, routes) -> bool:
    """产物里的路径是否对应一条后端路由

    段级比较，规则（宽严取舍：宁可少报也不错报 —— 闸门误报会让运维绕开它）：
    - 段数相同 → 逐段相等，或后端该段是路径参数 `{xxx}`（前端把 id 写死时命中）；
    - 后端路由更长 → 前端是它的前缀（模板串 `${id}` 被截断的情形，如 `/api/im/chats/`）。
    """
    front = _split(front_path)
    if not front:
        return False
    for r in sorted(routes):
        seg = _split(r)
        if len(seg) < len(front):
            continue
        if all(seg[i] == front[i] or seg[i].startswith("{") for i in range(len(front))):
            return True
    return False


def api_paths_missing(front_paths, routes) -> list:
    """返回「前端在调用、后端不存在」的路径（已排序去重）"""
    routes = set(routes)
    return sorted({p for p in set(front_paths) if p not in API_TRIVIAL and not route_exists(p, routes)})


def dump_api_paths(python: str, app_dir: Path, timeout: int = 180) -> tuple:
    """用**服务所用的解释器**导出后端路由表 → (路径集合, 说明)

    必须走 `app.openapi()["paths"]`：本项目 include_router 是惰性的，
    `app.routes` 里元素是 _IncludedRouter、path 为 None，直接读会得到空表。
    导入期不连数据库（engine 是惰性的），因此不会占连接池。
    """
    code = ("import json;from app.main import app;"
            "print('ROUTES:'+json.dumps(sorted(app.openapi()['paths'])))")
    try:
        r = subprocess.run([python, "-c", code], cwd=str(app_dir), capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=timeout)
    except (OSError, subprocess.SubprocessError) as e:
        return set(), f"无法执行 {python}：{type(e).__name__}: {e}"
    if r.returncode != 0:
        tail = ((r.stderr or "") + (r.stdout or "")).strip().splitlines()[-3:]
        return set(), "后端路由表导出失败：" + " | ".join(tail)
    for line in reversed((r.stdout or "").splitlines()):
        if line.startswith("ROUTES:"):
            try:
                routes = set(json.loads(line[len("ROUTES:"):]))
            except ValueError:
                break
            return routes, f"{len(routes)} 条路由"
    return set(), "后端路由表导出失败：未取得输出"


# ── CLI ──

def _resolve_dir(raw: str) -> Path:
    p = Path(raw)
    if not p.is_absolute():
        p = Path.cwd() / p
    return p.resolve()


def cmd_write(args) -> int:
    project = _resolve_dir(args.dir)
    info = write_build_info(project, note=args.note or "")
    print(f"[build-info] {project.name} 构建信息已写入 dist/.build-info.json")
    print(f"             源码指纹 {info['source_hash']}（{info['source_count']} 个文件）"
          f"；产物引用 {len(info['api_paths'])} 个 API 路径"
          f"；git {info.get('git_sha') or '未知'}{'（有未提交改动）' if info.get('git_dirty') else ''}")
    return 0


def cmd_needs_build(args) -> int:
    project = _resolve_dir(args.dir)
    need, why = needs_build(project)
    if args.explain or need:
        print(f"[build-info] {project.name}：{'需要构建' if need else '无需构建'} —— {why}")
    return 0 if need else 1


def cmd_show(args) -> int:
    project = _resolve_dir(args.dir)
    info = read_build_info(project)
    if info is None:
        print(f"[build-info] {project.name}：无构建信息（dist/.build-info.json 不存在或损坏）")
        return 1
    need, why = needs_build(project)
    print(f"[build-info] {project.name}")
    print(f"  构建时间：{info.get('built_at')}")
    print(f"  git：     {info.get('git_sha') or '未知'}"
          f"{'（构建时有未提交改动）' if info.get('git_dirty') else ''}")
    print(f"  源码指纹：{info.get('source_hash')}（{info.get('source_count')} 个文件）")
    print(f"  产物：    {len(info.get('assets') or [])} 个文件"
          f"，引用 {len(info.get('api_paths') or [])} 个 API 路径")
    print(f"  新鲜度：  {'已过期 —— ' + why if need else why}")
    if need:
        for line in changed_sources(project, info)[:10]:
            print(f"            · {line}")
    return 0


def cmd_check(args) -> int:
    """校验新鲜度 + 前后端契约（供运维手动排查；部署闸门走 preflight 调用同一套函数）"""
    project = _resolve_dir(args.dir)
    rc = 0
    need, why = needs_build(project)
    info = read_build_info(project)
    if need:
        rc = 1
        print(f"[build-info] [过期] {project.name} 的 dist 与当前源码不匹配 —— {why}")
        if info is not None:
            for line in changed_sources(project, info)[:10]:
                print(f"          · {line}")
        print("          处理：重新构建该前端（deploy.sh 会在源码变更时自动重建）")
    else:
        print(f"[build-info] [ OK ] {project.name} 的 dist 与当前源码一致（{why}）")

    if info is None:
        return rc
    routes, note = dump_api_paths(args.python, Path(args.app_dir).resolve())
    if not routes:
        print(f"[build-info] [WARN] 跳过前后端契约比对 —— {note}")
        return rc
    missing = api_paths_missing(info.get("api_paths") or [], routes)
    if missing:
        rc = 1
        print(f"[build-info] [WARN] {len(missing)} 个路径前端在调用但后端不存在"
              f"（接口改名/删除后前端未跟上，线上表现为按钮静默失效）：")
        for p in missing[:20]:
            print(f"          · {p}")
    else:
        print(f"[build-info] [ OK ] {len(info.get('api_paths') or [])} 个前端引用路径"
              f"全部对应到后端路由（共 {len(routes)} 条）")
    return rc


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="前端构建溯源与前后端契约一致性检查")
    sub = p.add_subparsers(dest="cmd", required=True)

    w = sub.add_parser("write", help="构建后写入 dist/.build-info.json")
    w.add_argument("--dir", required=True, help="前端工程目录（如 web）")
    w.add_argument("--note", default="", help="备注（写进构建信息，便于追溯）")
    w.set_defaults(func=cmd_write)

    n = sub.add_parser("needs-build", help="判断是否需要重建（退出码 0=需要，1=不需要）")
    n.add_argument("--dir", required=True)
    n.add_argument("--explain", action="store_true", help="无论结果都打印原因")
    n.set_defaults(func=cmd_needs_build)

    s = sub.add_parser("show", help="查看已记录的构建信息")
    s.add_argument("--dir", required=True)
    s.set_defaults(func=cmd_show)

    c = sub.add_parser("check", help="校验 dist 新鲜度与前后端契约")
    c.add_argument("--dir", required=True)
    c.add_argument("--app-dir", default="", help="项目根目录（导出后端路由表用，默认自动推断）")
    c.add_argument("--python", default=sys.executable, help="服务所用解释器")
    c.set_defaults(func=cmd_check)

    args = p.parse_args(argv)
    if args.cmd == "check" and not args.app_dir:
        # tools/build_info.py → 项目根
        args.app_dir = str(Path(__file__).resolve().parent.parent)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
