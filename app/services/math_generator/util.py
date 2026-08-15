"""数学题答案格式化工具（修复整数除法截断导致的错误答案）

背景：折扣/利润/百分数题曾用 `price * discount // 100` 整数除法，导致
202 打八折算成 161（应为 161.6）。统一改为浮点计算 + 本工具去尾零格式化。
"""


def fmt_num(x, decimals: int = 2) -> str:
    """四舍五入并去掉无意义的小数尾零，返回字符串。

    例：
        fmt_num(161.6)   -> '161.6'
        fmt_num(160.0)   -> '160'
        fmt_num(178.35)  -> '178.35'
        fmt_num(120)     -> '120'

    容错：无法转浮点时原样返回字符串。
    """
    try:
        v = round(float(x) + 1e-9, decimals)
    except (TypeError, ValueError):
        return str(x)
    s = f"{v:.{decimals}f}"
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s
