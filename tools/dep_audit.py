"""依赖完整性审计：找出「代码硬导入、但 requirements.txt 未声明」的第三方包

为什么需要它
------------
这类缺陷的表现是「本地一切正常，线上一起就崩」，而且崩在应用导入期 ——
uvicorn 直接启动失败、全站 502，但本地跑测试全绿，最难查：

- 本地 `.venv` 往往因为跑测试（TestClient 需要 httpx）或历史安装，比线上多装了包；
- 线上 `deploy.sh` 只执行 `pip install -r requirements.txt`，严格按清单建环境；
- 于是同一份代码，本地 `import httpx` 通过、线上抛 `ModuleNotFoundError`。

**2026-09-24 线上事故即由此产生**：commit 7c7592c 把 `weather.py` 从 requests 改成
httpx 异步（消除线程池阻塞，改动本身是对的），但没有同步 `requirements.txt`；
线上启动即 `ModuleNotFoundError: No module named 'httpx'`，
崩在 `app/main.py:24` 的 platform 路由导入处（其中包含 weather）。
故新增本审计，并接进 `tools/regression_check.py`（第 6 项）与 pytest。

判定规则（只看「启动期硬依赖」，避免误报）
------------------------------------------
算作硬依赖（缺失即启动失败，报错）：
- **模块级** import —— 模块被导入时立即执行；函数/类体内的 import 是调用时才执行，不算；
- 且在 `try:` **之外** —— 包在 try 里属于**优雅降级**（如 bs4 缺失时回落 `_BS4 = False`），不算；
- 且不在 `if TYPE_CHECKING:` 内（类型检查专用，运行期不执行）。

模块名 ≠ 发行包名的处理
-----------------------
优先用 `importlib.metadata.packages_distributions()` 反查所有者
（docx→python-docx、bs4→beautifulsoup4、dotenv→python-dotenv …），
查不到再退回内置 `ALIAS` 表；两者都查不到时按「无法判定」列为提示级，不计失败。

用法
----
    .venv/Scripts/python.exe tools/dep_audit.py          # 审计 app/（有错误返回 1）
    .venv/Scripts/python.exe tools/dep_audit.py --all    # 连 tools/ 一起审计
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REQUIREMENTS = ROOT / "requirements.txt"

# 模块名 -> 发行包名的兜底映射（仅在 packages_distributions() 查不到时使用）
ALIAS = {
    "docx": "python-docx",
    "dotenv": "python-dotenv",
    "yaml": "PyYAML",
    "PIL": "pillow",
    "bs4": "beautifulsoup4",
    "fitz": "PyMuPDF",
    "pymupdf": "PyMuPDF",
    "multipart": "python-multipart",
    "pymysql": "PyMySQL",
    "dateutil": "python-dateutil",
    "jwt": "PyJWT",
    "OpenSSL": "pyOpenSSL",
    "serial": "pyserial",
    "sklearn": "scikit-learn",
    "cv2": "opencv-python",
    "edge_tts": "edge-tts",
    "pypinyin": "pypinyin",
}


def norm(name: str) -> str:
    """包名归一化：不区分大小写、`-`/`_`/`.` 视为等价"""
    return name.strip().lower().replace("-", "_").replace(".", "_")


# ── requirements.txt 解析 ──

def declared_distributions(path: Path | None = None) -> dict:
    """返回 {归一化包名: 版本} —— 只认 `name==version` / `name>=version` 形式的行

    `path` 省略时读项目根 requirements.txt；显式传入是为了便于测试（注入模拟清单）。
    """
    path = path or REQUIREMENTS
    out: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        # 去掉环境标记与 extras：'pkg[extra]==1.0 ; python_version>="3"'
        head = line.split(";")[0].strip()
        for sep in ("==", ">=", "~=", "<=", ">", "<"):
            if sep in head:
                name, _, ver = head.partition(sep)
                out[norm(name.split("[")[0])] = ver.strip()
                break
        else:
            out[norm(head.split("[")[0])] = ""
    return out


# ── 硬导入收集 ──

def _top_names(node: ast.AST) -> list[str]:
    """取 import 语句的顶层模块名；相对导入（本地模块）返回空"""
    if isinstance(node, ast.Import):
        return [a.name.split(".")[0] for a in node.names]
    if isinstance(node, ast.ImportFrom):
        if node.level:          # from . / from .. —— 本地模块
            return []
        return [node.module.split(".")[0]] if node.module else []
    return []


def _is_type_checking(test: ast.expr) -> bool:
    """判断 `if TYPE_CHECKING:` / `if typing.TYPE_CHECKING:`"""
    if isinstance(test, ast.Name):
        return test.id == "TYPE_CHECKING"
    if isinstance(test, ast.Attribute):
        return test.attr == "TYPE_CHECKING"
    return False


def hard_imports(path: Path) -> list[tuple[str, int]]:
    """收集文件中的「启动期硬导入」-> [(顶层模块名, 行号)]

    只保留：模块级、不在 try 内、不在 if TYPE_CHECKING 内的 import。
    """
    tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
    found: list[tuple[str, int]] = []

    def visit(node: ast.AST, guarded: bool) -> None:
        for child in ast.iter_child_nodes(node):
            # 函数 / 类 / lambda 体内的 import 是调用时才执行，不影响启动
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
                continue
            # try 块内的 import 视为优雅降级（缺失时由代码自行兜底）
            if isinstance(child, (ast.Try, getattr(ast, "TryStar", ast.Try))):
                for sub in ast.iter_child_nodes(child):
                    visit(sub, True)
                continue
            # 类型检查专用分支，运行期不执行
            if isinstance(child, ast.If) and _is_type_checking(child.test):
                continue
            if isinstance(child, (ast.Import, ast.ImportFrom)):
                if not guarded:
                    for name in _top_names(child):
                        found.append((name, child.lineno))
                continue
            visit(child, guarded)

    visit(tree, False)
    return found


# ── 审计主逻辑 ──

def _pkg_map() -> dict:
    """{顶层模块名: [发行包名]} —— 来自已安装包的元数据"""
    try:
        from importlib.metadata import packages_distributions
        return packages_distributions()
    except Exception:            # pragma: no cover - 极老版本环境
        return {}


def _local_names(root: Path = ROOT) -> set[str]:
    """本地包/模块名（app、tools、data …），这些不是第三方依赖"""
    names = {"app", "tools", "tests"}
    for p in root.iterdir():
        if p.name.startswith(".") or p.name == "venv":
            continue
        if p.is_dir() or p.suffix == ".py":
            names.add(p.stem if p.suffix == ".py" else p.name)
    return names


def audit(paths: list[Path], root: Path = ROOT, requirements: Path | None = None) -> dict:
    """审计给定目录下的「启动期硬导入」是否都在 requirements.txt 声明

    返回 {"errors": [...], "warnings": [...], "stats": {...}}
      errors   —— 硬导入指向的发行包未声明（线上必崩）
      warnings —— 无法判定归属（本地也没装），需人工确认
    """
    declared = declared_distributions(requirements)
    pkg_map = _pkg_map()
    local = _local_names(root)
    stdlib = set(sys.stdlib_module_names)

    errors: list[dict] = []
    warnings: list[dict] = []
    third: dict[str, dict] = {}

    for base in paths:
        for f in sorted(base.rglob("*.py")):
            for name, lineno in hard_imports(f):
                if name in stdlib or name in local or name.startswith("_"):
                    continue
                third.setdefault(name, {"files": [], "resolved": False})
                third[name]["files"].append(f"{f.relative_to(root)}:{lineno}")

    for name, info in sorted(third.items()):
        owners = {norm(o) for o in pkg_map.get(name, [])}
        if owners:
            info["resolved"] = True
            candidates = owners
        elif name in ALIAS:
            info["resolved"] = True
            candidates = {norm(ALIAS[name])}
        else:
            # 归属未知：按同名假设判定（多数纯 Python 包模块名与包名一致）
            candidates = {norm(name)}

        hit = sorted(candidates & set(declared))
        if hit:
            info["dist"] = hit[0]
            continue
        info["dist"] = sorted(owners or candidates)[0]
        item = {
            "module": name,
            "dist": info["dist"],
            "files": sorted(info["files"]),
            "resolved": info["resolved"],
        }
        (errors if info["resolved"] else warnings).append(item)

    return {
        "errors": errors,
        "warnings": warnings,
        "stats": {
            "declared": len(declared),
            "third_party_modules": len(third),
            "files_scanned": sum(1 for b in paths for _ in b.rglob("*.py")),
        },
    }


def format_report(result: dict) -> str:
    lines: list[str] = []
    st = result["stats"]
    lines.append(f"扫描 {st['files_scanned']} 个 .py；requirements 声明 {st['declared']} 个包；"
                 f"启动期硬依赖 {st['third_party_modules']} 个第三方模块")
    if result["errors"]:
        lines.append("")
        lines.append("【错误】以下包被模块级硬导入，但 requirements.txt 未声明 -> 线上启动必崩：")
        for e in result["errors"]:
            lines.append(f"  ✗ {e['module']}  (发行包 {e['dist']})")
            for f in e["files"][:5]:
                lines.append(f"      {f}")
        lines.append("")
        lines.append("  修复：把对应包（含版本）加进 requirements.txt，"
                     "线上再 `git pull && bash deploy.sh`（deploy.sh 会 pip install -r requirements.txt）")
    if result["warnings"]:
        lines.append("")
        lines.append("【提示】无法判定归属（本地也未安装），请人工确认是否需要声明：")
        for w in result["warnings"]:
            lines.append(f"  ? {w['module']} -> {w['files'][:3]}")
    if not result["errors"] and not result["warnings"]:
        lines.append("")
        lines.append("✅ app/ 的启动期硬导入全部已在 requirements.txt 中声明")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    paths = [ROOT / "app"]
    if "--all" in argv:
        paths.append(ROOT / "tools")
    print("=" * 68)
    print("依赖完整性审计（启动期硬导入 vs requirements.txt）")
    print("=" * 68)
    print("审计范围：" + ", ".join(str(p.relative_to(ROOT)) for p in paths))
    print()
    result = audit(paths)
    print(format_report(result))
    print()
    print("=" * 68)
    if result["errors"]:
        print(f"结论：{len(result['errors'])} 个未声明依赖（线上会启动失败）")
        print("=" * 68)
        return 1
    print("结论：通过")
    print("=" * 68)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
