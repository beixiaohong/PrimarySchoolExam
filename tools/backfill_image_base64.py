"""主库 questions.image_base64 回填工具

需求背景：原题库（primary_school.db.questions）中 93 道题目带有 image_path，
但部分文件路径已失效（如 /output/figures/*.png 在当前环境不存在）。
本工具扫描所有带 image_path 的题目，尝试读取图片文件并转成 base64 写入 image_base64；
文件缺失则跳过并统计，便于后续改由生成器直接产出 base64。

用法：
  python tools/backfill_image_base64.py
  python tools/backfill_image_base64.py --search-dir output/figures
"""
import argparse
import base64
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import select, update  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.models.exam import Question  # noqa: E402

MIME = {
    '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png',
    '.gif': 'image/gif', '.bmp': 'image/bmp', '.svg': 'image/svg+xml',
}


def _resolve(path, search_dirs):
    """按 image_path 定位真实图片文件，支持绝对/相对/仅文件名三种查找策略。

    Args:
        path: 题目中存储的图片路径（可能绝对、相对或仅文件名）。
        search_dirs: 额外搜索目录列表（Path），优先于仅文件名回退。
    Returns:
        str | None: 命中则返回文件路径，未找到返回 None（调用方计为缺失）。
    副作用：只读文件系统，不改库。
    """
    if os.path.isabs(path) and os.path.exists(path):
        return path
    # 相对路径：尝试项目根 + 各搜索目录
    for base in [ROOT] + search_dirs:
        cand = os.path.join(str(base), path.lstrip("/\\"))
        if os.path.exists(cand):
            return cand
    # 仅文件名：在搜索目录中查找
    name = os.path.basename(path)
    for base in search_dirs:
        cand = os.path.join(str(base), name)
        if os.path.exists(cand):
            return cand
    return None


def main():
    """回填 questions.image_base64：扫描带 image_path 的题目，读取图片转 base64 写入。

    参数：--search-dir 可多次指定额外图片搜索目录。
    副作用：① 幂等确保 questions 表存在 image_base64 列（ALTER ADD COLUMN）；
            ② 对缺失 base64 的题目 UPDATE 写入 data:<mime>;base64,...；文件缺失则跳过统计。
    注意：会直接修改线上题目表数据；ALTER 加列若已存在会自动忽略报错。
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--search-dir", action="append", default=[],
                        help="除项目根外，额外搜索图片的目录（可多次）")
    args = parser.parse_args()
    # 确保 image_base64 列已存在（跨 dialect 幂等加列）；显式打印错误便于排查
    from app.database import init_db, engine
    from sqlalchemy import text
    init_db()
    # 本项目已移除 SQLite：统一 MySQL，其 TEXT/MEDIUMTEXT 列不允许有 DEFAULT 值，故不带 DEFAULT。
    col_def = "MEDIUMTEXT"
    try:
        with engine.connect() as c:
            # 【危险操作】ALTER TABLE ADD COLUMN 加列（已存在时报错，可忽略）
            c.execute(text(f"ALTER TABLE questions ADD COLUMN image_base64 {col_def}"))
            c.commit()
        print("✅ 已确保 questions.image_base64 列存在")
    except Exception as e:
        print(f"⚠️ 新增 image_base64 列时（若已存在可忽略）: {e!r}")
    search_dirs = [Path(d) for d in args.search_dir]

    recovered = 0
    missing = 0
    skipped = 0
    with SessionLocal() as session:
        rows = session.execute(
            select(Question).where(Question.image_path != "")
        ).scalars().all()
        for q in rows:
            if q.image_base64:  # 已回填则跳过
                skipped += 1
                continue
            real = _resolve(q.image_path, search_dirs)
            if not real:
                missing += 1
                continue
            try:
                with open(real, 'rb') as f:
                    b64 = base64.b64encode(f.read()).decode()
                ext = os.path.splitext(real)[1].lower()
                # 写回 base64（随下方 session.commit 一并 UPDATE 题目表）
                q.image_base64 = f"data:{MIME.get(ext, 'image/png')};base64,{b64}"
                recovered += 1
            except Exception:
                missing += 1
        session.commit()

    print(f"✅ 完成：已恢复 {recovered} 张 | 缺失/跳过 {missing} 张 | 已存在 {skipped} 张"
          f"（共扫描 {recovered + missing + skipped} 条带 image_path 的题目）")
    if missing:
        print("⚠️ 仍有图片文件缺失，建议后续由生成器直接产出 image_base64，而非依赖 image_path。")


if __name__ == "__main__":
    main()
