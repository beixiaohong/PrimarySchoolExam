#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
TurboFieldfare 自动代码注释工具

支持:
.py .html .js .css

功能:
- 配置扫描目录
- 调用本地 TurboFieldfare API
- 自动备份 .bak
- 直接覆盖原文件
"""

import os
import shutil
import time
from openai import OpenAI


# ==========================
# 配置区域
# ==========================

# 相对于本文件所在目录
SCAN_DIRS = [
    "app",
    "templates",
    "static",
]


EXTENSIONS = {
    ".py",
    ".html",
    ".js",
    ".css",
}


IGNORE_DIRS = {
    ".git",
    "node_modules",
    "dist",
    "build",
    ".venv",
    "venv",
    "__pycache__",
}


IGNORE_FILES = {
    "ai_comment.py",
}


MAX_FILE_SIZE = 300 * 1024


client = OpenAI(
    base_url="http://127.0.0.1:8080/v1",
    api_key="none",
    timeout=300,
)

MODEL = "gemma-4-26b-a4b-it"


# ==========================
# AI调用
# ==========================

def call_ai(filename, code):
    prompt = f"""
你是一个资深软件工程师。

请给下面代码添加中文注释。

要求：
1. 不修改代码逻辑
2. 不修改变量名
3. 不删除代码
4. 不重构代码
5. 保留原格式
6. 只增加必要注释
7. 返回完整代码，不要解释

文件:
{filename}

代码:
{code}
"""

    result = client.chat.completions.create(
        model=MODEL,
        messages=[
            {
                "role": "system",
                "content": "你是代码注释专家"
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        temperature=0.2,
        max_tokens=4000
    )

    return result.choices[0].message.content


# ==========================
# 处理文件
# ==========================

def process_file(path):

    print("\n处理:", path)

    if os.path.getsize(path) > MAX_FILE_SIZE:
        print("文件过大，跳过")
        return

    try:
        with open(path, "r", encoding="utf-8") as f:
            old_code = f.read()

    except Exception as e:
        print("读取失败:", e)
        return

    start = time.time()

    try:
        new_code = call_ai(path, old_code)
    except Exception as e:
        print("AI调用失败:", e)
        return

    if not new_code.strip():
        print("AI返回为空")
        return

    backup = path + ".bak"

    if not os.path.exists(backup):
        shutil.copy2(path, backup)

    with open(path, "w", encoding="utf-8") as f:
        f.write(new_code)

    print("完成 %.2f 秒" % (time.time() - start))


# ==========================
# 扫描目录
# ==========================

def scan_directory(directory):

    root_dir = os.path.dirname(
        os.path.abspath(__file__)
    )

    target = os.path.join(
        root_dir,
        directory
    )

    if not os.path.exists(target):
        print("目录不存在:", target)
        return

    for root, dirs, files in os.walk(target):

        dirs[:] = [
            d for d in dirs
            if d not in IGNORE_DIRS
        ]

        for file in files:

            if file in IGNORE_FILES:
                continue

            ext = os.path.splitext(file)[1].lower()

            if ext not in EXTENSIONS:
                continue

            process_file(
                os.path.join(root, file)
            )


if __name__ == "__main__":

    print("TurboFieldfare代码注释开始")

    for d in SCAN_DIRS:
        scan_directory(d)

    print("\n全部完成")
