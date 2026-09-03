"""端点基线快照工具（S1-R 模块化搬迁 · 红线「端点总数不变」自检口径）

用法：
    .venv\\Scripts\\python.exe tools\\endpoint_snapshot.py [输出文件]

遍历 app.routes 输出排序后的 "METHOD path" 清单（含静态挂载 MOUNT 与 /health、/、/admin
等系统端点，消除历史 374 vs 377 的口径分歧），默认写入仓库根 endpoint_baseline.txt。
每个域搬迁完成后重跑本脚本并与基线 diff，要求零差异（或书面列明增减理由）。
GET 路由自动附带的 HEAD 不计入，保证清单稳定。
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def collect_routes(app) -> list:
    """收集全部路由：APIRoute 按方法逐行输出，WebSocket 输出 WS 行，Mount 输出 MOUNT 行。

    注意：FastAPI 0.140+ 的 include_router 为惰性挂载（app.routes 中是
    _IncludedRouter，不直接展开 path），需递归 effective_candidates() 取出
    已拼好前缀的 _EffectiveRouteContext.starlette_route 才是真实端点。
    用类型名判断而非 import 私有类，降低版本耦合。
    """
    lines = set()

    def _emit(path, methods, kind):
        if path is None:
            return
        if kind == "ws":
            lines.add(f"WS {path}")
        elif kind == "mount":
            lines.add(f"MOUNT {path}")
        else:
            for m in sorted(methods or []):
                if m == "HEAD":  # FastAPI 为 GET 自动附加，不计入基线
                    continue
                lines.add(f"{m} {path}")

    def _plain(r):
        """顶层普通路由（APIRoute/Route/Mount）。"""
        tn = type(r).__name__
        path = getattr(r, "path", None)
        if tn == "Mount":
            _emit(path, None, "mount")
        elif "WebSocket" in tn:
            _emit(path, None, "ws")
        else:
            _emit(path, getattr(r, "methods", None), "http")

    def _walk(items):
        for r in items:
            tn = type(r).__name__
            if tn == "_IncludedRouter":
                _walk(r.effective_candidates())
                _walk(r.effective_low_priority_routes())
            elif tn == "_EffectiveRouteContext":
                sr = getattr(r, "starlette_route", None)
                orig = getattr(r, "original_route", sr)
                # APIRoute 类：context 自带拼好前缀的 .path/.methods（starlette_route 为 None）；
                # Starlette 原生类（WS/Mount/Route）：全路径在 starlette_route.path。
                path = (getattr(r, "path", None)
                        or getattr(sr, "path", None)
                        or getattr(orig, "path", None))
                oname = type(orig).__name__
                if "WebSocket" in oname or "WebSocket" in type(sr or "").__name__:
                    _emit(path, None, "ws")
                elif oname == "Mount" or type(sr).__name__ == "Mount":
                    _emit(path, None, "mount")
                else:
                    _emit(path, getattr(r, "methods", None)
                          or getattr(orig, "methods", None), "http")
            else:
                _plain(r)

    _walk(app.routes)
    return sorted(lines)


def main():
    from app.main import app
    lines = collect_routes(app)
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "endpoint_baseline.txt"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[snapshot] 共 {len(lines)} 条端点/挂载 → {out}")


if __name__ == "__main__":
    main()
