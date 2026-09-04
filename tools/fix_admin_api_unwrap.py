# -*- coding: utf-8 -*-
"""机械化修正 admin 前端 axios 响应解包错误。

背景
----
admin/src/api/index.js 的响应拦截器是 `(res) => res`，即**返回完整 axios 响应对象**，
正确取业务数据需 `const { data } = await api.get(...)` 或 `(await api.get(...)).data`。

但 Users / Textbooks / Content 以及本轮新增的 Commerce / Rbac / Audit /
Annotation / Mastery 共 8 个页面写成了：

    const d = await api.get('/api/admin/users', { params })
    rows.value = (d && d.items) || []      // ← d 是响应对象，d.items 恒为 undefined

于是所有列表页恒为空数组 —— 这正是「除首页/运营分析/数据中心外，后台页面全空」的根因
（能正常显示数据的页面用的都是 `const { data } = await api.get(...)`）。

修正规则
--------
    const d = await api.<method>(   →   const { data: d } = await api.<method>(

例外（不改）
------------
    const r = await api.get(url, { responseType: 'blob' })   // 需要 r.data 拿 Blob

用法
----
    python tools/fix_admin_api_unwrap.py            # 预演，只报告
    python tools/fix_admin_api_unwrap.py --apply    # 实际写入
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VIEWS_DIR = ROOT / "admin" / "src" / "views"

# 只改写变量名为 d 的赋值；r（blob 下载）必须保持完整响应对象
PATTERN = re.compile(r"(?m)^(\s*)const d = await (api\.(?:get|post|put|delete)\()")


def main() -> int:
    apply = "--apply" in sys.argv

    if not VIEWS_DIR.is_dir():
        print(f"[错误] 目录不存在：{VIEWS_DIR}")
        return 1

    total_files = 0
    total_hits = 0

    for vue_file in sorted(VIEWS_DIR.glob("*.vue")):
        src = vue_file.read_text(encoding="utf-8")
        hits = PATTERN.findall(src)
        if not hits:
            continue

        total_files += 1
        total_hits += len(hits)
        print(f"  {vue_file.name:<18} {len(hits):>2} 处")
        for indent, call in hits:
            print(f"      {indent}const d = await {call}...")

        if apply:
            new_src = PATTERN.sub(r"\1const { data: d } = await \2", src)
            if new_src != src:
                vue_file.write_text(new_src, encoding="utf-8")

    print()
    print(f"合计：{total_files} 个文件、{total_hits} 处")
    if apply:
        print("已写入（const d = await api.X  →  const { data: d } = await api.X）")
    else:
        print("预演模式，未修改任何文件。加 --apply 实际写入。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
