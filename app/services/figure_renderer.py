"""图形渲染服务

用 matplotlib 为几何题生成配图，保存到 output/figures/ 目录。
返回相对路径（如 /output/figures/xxx.png），前端和 Word 文档均可引用。
"""
import os
import uuid
import math
import random
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # 无头模式，不需要显示器
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.patches import FancyArrowPatch
import numpy as np

# 中文字体设置
plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

FIGURE_DIR = Path(__file__).resolve().parent.parent.parent / "output" / "figures"
FIGURE_DIR.mkdir(parents=True, exist_ok=True)


def _save_fig(fig) -> str:
    """保存图片，返回 web 可访问的相对路径"""
    filename = f"{uuid.uuid4().hex[:12]}.png"
    filepath = FIGURE_DIR / filename
    fig.savefig(str(filepath), dpi=120, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return f"/output/figures/{filename}"


def render_triangle(base: float, height: float, labels: dict = None) -> str:
    """渲染三角形（标注底和高）"""
    fig, ax = plt.subplots(1, 1, figsize=(4, 3))
    # 三角形顶点
    A = (0, 0)
    B = (base, 0)
    C = (base * random.uniform(0.3, 0.7), height)

    triangle = plt.Polygon([A, B, C], fill=False, edgecolor="black", linewidth=1.5)
    ax.add_patch(triangle)

    # 标注顶点
    ax.annotate("A", A, textcoords="offset points", xytext=(-10, -10), fontsize=11)
    ax.annotate("B", B, textcoords="offset points", xytext=(5, -10), fontsize=11)
    ax.annotate("C", C, textcoords="offset points", xytext=(0, 8), fontsize=11)

    # 标注底和高
    ax.annotate("", xy=(base / 2, 0), xytext=(base / 2, -0.3),
                arrowprops=dict(arrowstyle="<->", color="blue"))
    ax.text(base / 2, -0.6, f"底={base}", ha="center", fontsize=10, color="blue")

    # 高（虚线）
    foot_x = C[0]
    ax.plot([foot_x, foot_x], [0, height], "r--", linewidth=1)
    ax.text(foot_x + 0.2, height / 2, f"高={height}", fontsize=10, color="red")

    ax.set_xlim(-1, base + 1)
    ax.set_ylim(-1.5, height + 1)
    ax.set_aspect("equal")
    ax.axis("off")
    return _save_fig(fig)


def render_rectangle(length: float, width: float) -> str:
    """渲染长方形（标注长和宽）"""
    fig, ax = plt.subplots(1, 1, figsize=(4, 3))
    rect = patches.Rectangle((0, 0), length, width, linewidth=1.5,
                              edgecolor="black", facecolor="none")
    ax.add_patch(rect)

    ax.text(length / 2, -0.4, f"长={length}", ha="center", fontsize=10, color="blue")
    ax.text(-0.4, width / 2, f"宽={width}", ha="center", fontsize=10,
            color="blue", rotation=90)

    ax.set_xlim(-1, length + 1)
    ax.set_ylim(-1, width + 1)
    ax.set_aspect("equal")
    ax.axis("off")
    return _save_fig(fig)


def render_circle(radius: float) -> str:
    """渲染圆（标注半径和圆心）"""
    fig, ax = plt.subplots(1, 1, figsize=(3.5, 3.5))
    circle = plt.Circle((0, 0), radius, fill=False, edgecolor="black", linewidth=1.5)
    ax.add_patch(circle)

    # 圆心
    ax.plot(0, 0, "ko", markersize=4)
    ax.text(0.1, 0.1, "O", fontsize=11)

    # 半径
    angle = random.uniform(0.3, 1.2)
    rx = radius * math.cos(angle)
    ry = radius * math.sin(angle)
    ax.plot([0, rx], [0, ry], "b-", linewidth=1.2)
    ax.text(rx / 2 + 0.2, ry / 2 + 0.2, f"r={radius}", fontsize=10, color="blue")

    ax.set_xlim(-radius - 1, radius + 1)
    ax.set_ylim(-radius - 1, radius + 1)
    ax.set_aspect("equal")
    ax.axis("off")
    return _save_fig(fig)


def render_coordinate(points: list, title: str = "") -> str:
    """渲染坐标系中标注的点"""
    fig, ax = plt.subplots(1, 1, figsize=(4, 4))
    ax.axhline(y=0, color="black", linewidth=0.8)
    ax.axvline(x=0, color="black", linewidth=0.8)
    ax.set_xlabel("x", fontsize=11)
    ax.set_ylabel("y", fontsize=11)

    labels = "ABCDEFGH"
    for i, (x, y) in enumerate(points):
        ax.plot(x, y, "ro", markersize=6)
        label = labels[i] if i < len(labels) else f"P{i+1}"
        ax.annotate(f"{label}({x},{y})", (x, y),
                    textcoords="offset points", xytext=(5, 5), fontsize=9)

    ax.set_xlim(-1, 11)
    ax.set_ylim(-1, 11)
    ax.set_xticks(range(0, 11))
    ax.set_yticks(range(0, 11))
    ax.grid(True, alpha=0.3)
    if title:
        ax.set_title(title, fontsize=11)
    return _save_fig(fig)


def render_bar_chart(categories: list, values: list, title: str = "统计图") -> str:
    """渲染条形统计图"""
    fig, ax = plt.subplots(1, 1, figsize=(5, 3.5))
    colors = ["#4361ee", "#2ec4b6", "#ff9f1c", "#e71d36", "#7209b7", "#3a86a8"]
    bars = ax.bar(categories, values, color=colors[:len(categories)], width=0.6)
    ax.set_title(title, fontsize=12)
    ax.set_ylabel("数量", fontsize=10)
    for bar, val in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.3,
                str(val), ha="center", fontsize=10)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    return _save_fig(fig)


def render_pie_chart(categories: list, values: list, title: str = "占比图") -> str:
    """渲染扇形统计图"""
    fig, ax = plt.subplots(1, 1, figsize=(4, 4))
    colors = ["#4361ee", "#2ec4b6", "#ff9f1c", "#e71d36", "#7209b7", "#3a86a8"]
    ax.pie(values, labels=categories, autopct="%1.1f%%",
           colors=colors[:len(categories)], startangle=90)
    ax.set_title(title, fontsize=12)
    return _save_fig(fig)


def render_line_graph(x_labels: list, y_values: list, title: str = "折线统计图") -> str:
    """渲染折线统计图"""
    fig, ax = plt.subplots(1, 1, figsize=(5, 3.5))
    ax.plot(x_labels, y_values, "o-", color="#4361ee", linewidth=2, markersize=6)
    ax.set_title(title, fontsize=12)
    ax.set_ylabel("数值", fontsize=10)
    ax.grid(True, alpha=0.3)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    for x, y in zip(x_labels, y_values):
        ax.annotate(str(y), (x, y), textcoords="offset points",
                    xytext=(0, 8), ha="center", fontsize=9)
    return _save_fig(fig)


def render_trapezoid(top: float, bottom: float, height: float) -> str:
    """渲染梯形（标注上底、下底、高）"""
    fig, ax = plt.subplots(1, 1, figsize=(4.5, 3))
    offset = (bottom - top) / 2
    verts = [(0, 0), (bottom, 0), (offset + top, height), (offset, height)]
    trap = plt.Polygon(verts, fill=False, edgecolor="black", linewidth=1.5)
    ax.add_patch(trap)

    ax.text(bottom / 2, -0.5, f"下底={bottom}", ha="center", fontsize=10, color="blue")
    ax.text(offset + top / 2, height + 0.3, f"上底={top}", ha="center", fontsize=10, color="blue")
    # 高（虚线）
    mid_x = bottom / 2
    ax.plot([mid_x, mid_x], [0, height], "r--", linewidth=1)
    ax.text(mid_x + 0.3, height / 2, f"高={height}", fontsize=10, color="red")

    ax.set_xlim(-1, bottom + 1)
    ax.set_ylim(-1.2, height + 1)
    ax.set_aspect("equal")
    ax.axis("off")
    return _save_fig(fig)


def render_parallelogram(base: float, height: float) -> str:
    """渲染平行四边形（标注底和高）"""
    fig, ax = plt.subplots(1, 1, figsize=(4.5, 3))
    slant = base * 0.3
    verts = [(0, 0), (base, 0), (base + slant, height), (slant, height)]
    para = plt.Polygon(verts, fill=False, edgecolor="black", linewidth=1.5)
    ax.add_patch(para)

    ax.text(base / 2, -0.5, f"底={base}", ha="center", fontsize=10, color="blue")
    # 高
    ax.plot([slant, slant], [0, height], "r--", linewidth=1)
    ax.text(slant - 0.5, height / 2, f"高={height}", fontsize=10, color="red", rotation=90)

    ax.set_xlim(-1, base + slant + 1)
    ax.set_ylim(-1.2, height + 1)
    ax.set_aspect("equal")
    ax.axis("off")
    return _save_fig(fig)


def render_cuboid(length: float, width: float, height: float) -> str:
    """渲染长方体/正方体（3D透视）"""
    fig, ax = plt.subplots(1, 1, figsize=(4, 3.5))
    # 前面
    front = [(0, 0), (length, 0), (length, height), (0, height)]
    # 后面偏移
    dx, dy = width * 0.4, width * 0.3
    back = [(dx, dy), (length + dx, dy), (length + dx, height + dy), (dx, height + dy)]

    ax.add_patch(plt.Polygon(front, fill=False, edgecolor="black", linewidth=1.5))
    ax.add_patch(plt.Polygon(back, fill=False, edgecolor="gray", linewidth=1, linestyle="--"))
    # 连接线
    for f, b in zip(front, back):
        ax.plot([f[0], b[0]], [f[1], b[1]], "k-", linewidth=1)

    ax.text(length / 2, -0.5, f"长={length}", ha="center", fontsize=10, color="blue")
    ax.text(-0.5, height / 2, f"高={height}", ha="center", fontsize=10, color="blue", rotation=90)
    ax.text(length + dx / 2 + 0.3, -0.2, f"宽={width}", fontsize=10, color="blue")

    ax.set_xlim(-1.5, length + dx + 1)
    ax.set_ylim(-1.2, height + dy + 1)
    ax.set_aspect("equal")
    ax.axis("off")
    return _save_fig(fig)


def render_cylinder(radius: float, height: float) -> str:
    """渲染圆柱体"""
    fig, ax = plt.subplots(1, 1, figsize=(3.5, 4))
    # 用椭圆模拟顶底面
    ellipse_w = radius * 2
    ellipse_h = radius * 0.5

    # 底面椭圆
    bottom = patches.Ellipse((radius, 0), ellipse_w, ellipse_h,
                              fill=False, edgecolor="black", linewidth=1.5)
    # 顶面椭圆
    top = patches.Ellipse((radius, height), ellipse_w, ellipse_h,
                           fill=False, edgecolor="black", linewidth=1.5)
    ax.add_patch(bottom)
    ax.add_patch(top)
    # 两侧母线
    ax.plot([0, 0], [0, height], "k-", linewidth=1.5)
    ax.plot([radius * 2, radius * 2], [0, height], "k-", linewidth=1.5)

    # 标注
    ax.plot([radius, radius * 2], [0, 0], "b-", linewidth=1)
    ax.text(radius, -0.5, f"r={radius}", ha="center", fontsize=10, color="blue")
    ax.text(radius * 2 + 0.4, height / 2, f"高={height}", fontsize=10, color="blue", rotation=90)

    ax.set_xlim(-1, radius * 2 + 1.5)
    ax.set_ylim(-1.2, height + 1)
    ax.set_aspect("equal")
    ax.axis("off")
    return _save_fig(fig)


def render_cone(radius: float, height: float) -> str:
    """渲染圆锥体"""
    fig, ax = plt.subplots(1, 1, figsize=(3.5, 4))
    ellipse_w = radius * 2
    ellipse_h = radius * 0.5

    # 底面椭圆
    bottom = patches.Ellipse((radius, 0), ellipse_w, ellipse_h,
                              fill=False, edgecolor="black", linewidth=1.5)
    ax.add_patch(bottom)
    # 母线
    ax.plot([0, radius], [0, height], "k-", linewidth=1.5)
    ax.plot([radius * 2, radius], [0, height], "k-", linewidth=1.5)
    # 顶点
    ax.plot(radius, height, "ko", markersize=4)

    # 高（虚线）
    ax.plot([radius, radius], [0, height], "r--", linewidth=1)
    ax.text(radius + 0.3, height / 2, f"高={height}", fontsize=10, color="red", rotation=90)
    ax.text(radius / 2, -0.5, f"r={radius}", ha="center", fontsize=10, color="blue")

    ax.set_xlim(-1, radius * 2 + 1.5)
    ax.set_ylim(-1.2, height + 1)
    ax.set_aspect("equal")
    ax.axis("off")
    return _save_fig(fig)
