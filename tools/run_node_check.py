# -*- coding: utf-8 -*-
"""用 Python 驱动 node 跑前端校验（绕开沙箱 Bash fork 间歇失败）。

用法：
    python tools/run_node_check.py <js 脚本绝对路径>
输出同时打印到 stdout 并写入 .pc_cache/node_check_out.txt
"""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / ".pc_cache" / "node_check_out.txt"

NODE_CANDIDATES = [
    r"C:\Users\aaaa\.workbuddy\binaries\node\versions\22.22.2-2\node.exe",
    r"C:\Program Files\nodejs\node.exe",
    "node",
]


def find_node() -> str:
    import shutil

    for c in NODE_CANDIDATES:
        if c == "node":
            if shutil.which("node"):
                return "node"
            continue
        if Path(c).exists():
            return c
    raise SystemExit("[错误] 找不到可用的 node 可执行文件")


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1

    # 脚本路径一律转绝对路径：node 以 admin/ 为 cwd 运行（为解析 @vue/compiler-sfc），
    # 相对路径会被错误地拼接成 admin/<相对路径>
    script = Path(sys.argv[1]).resolve()
    if not script.exists():
        print(f"[错误] 脚本不存在：{script}")
        return 1

    node = find_node()
    env = dict(os.environ)
    # @vue/compiler-sfc 装在 admin/node_modules，脚本放在 .pc_cache，
    # 需靠 NODE_PATH 指过去，否则报 Cannot find module '@vue/compiler-sfc'
    node_modules = str(ROOT / "admin" / "node_modules")
    env["NODE_PATH"] = node_modules
    env.setdefault("PYTHONIOENCODING", "utf-8")

    print(f"[node] {node}")
    print(f"[cwd ] {ROOT / 'admin'}")
    print(f"[run ] {script}")
    print("-" * 60)

    proc = subprocess.run(
        [node, str(script)],
        cwd=str(ROOT / "admin"),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    combined = (proc.stdout or "") + (proc.stderr or "")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(combined, encoding="utf-8")

    print(combined)
    print("-" * 60)
    print(f"exit={proc.returncode}  (输出已写入 {OUT.relative_to(ROOT)})")
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
