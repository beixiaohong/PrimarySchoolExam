"""填空题答案容错判题（前端 app.js _matchAnswer 的 Python 镜像）

问题背景：孩子写简便方法的计算过程（如 "2*(999+1)=2*1000=2000"）会被
逐字比对判为错误。规则设计（前端/后端必须保持一致）：

1. 规范化后逐字相等 → 对
2. 正确答案含数字时（纯文字/古诗文/单词等不含数字 → 保持严格）：
   a. 按 "=" 分段，逐段剥离单位等非数学字符，安全求值（+ - * / 括号 小数 百分号）
   b. 任一用户段的值 ≈ 任一正确答案段的值 → 对（如 "2*(999+1)=2*1000=2000" ≈ "2000"）
   c. 兜底：正确答案仅 1 个数字 token 且该 token 在用户答案中出现 → 对
      双方数字 token 完全一致（忽略顺序容差）→ 对
3. 其余 → 错

安全性：不使用 eval；自定义递归下降解析器，只接受数字与 + - * / ( )。
除零、非法表达式返回 None（不匹配）。
"""
import re

_FW_DIGITS = str.maketrans("０１２３４５６７８９", "0123456789")
_FW_LOWER = str.maketrans("ａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ",
                          "abcdefghijklmnopqrstuvwxyz")
_FW_SYM = {"（": "(", "）": ")", "＝": "=", "，": ",", "。": ".",
           "×": "*", "＊": "*", "·": "*", "÷": "/", "＋": "+", "－": "-",
           "、": ","}   # 顿号当分隔符（"90、120、150" 与 "90,120,150" 等价）

_TRAIL_PUNC = "。！？；：、,.!?;:…"
_MATH_CHARS = re.compile(r"[0-9+\-*/().%]*\Z")


def _strip_annot(s: str) -> str:
    """剥离末尾括号注释（内容含非数学字符，如 （共6个）/（原式=1000×2=2000）），
    纯算式括号（如 2*(999+1)、(45)）保留，避免把数学表达式当注释剥掉。"""
    while True:
        m = re.search(r"\([^()]*\)\Z", s)
        if not m:
            return s
        if _MATH_CHARS.match(m.group(0)[1:-1]):   # 括号内全是数学字符 → 算式，停止
            return s
        t = s[: m.start()]
        if not t:
            return s
        s = t


def normalize_answer(s, keep_sep: bool = False) -> str:
    """规范化答案：小写、去空白、全角→半角、数学符号统一、去末尾标点与括号注释。
    keep_sep=True 时保留分隔符（顿号/逗号已归一为 ','），供数字 token 提取用。"""
    if s is None:
        return ""
    s = str(s).strip().lower()
    s = re.sub(r"\s+", "", s)
    s = s.translate(_FW_DIGITS).translate(_FW_LOWER)
    for k, v in _FW_SYM.items():
        s = s.replace(k, v)
    s = s.rstrip(_TRAIL_PUNC)
    s = _strip_annot(s)          # "90、120、…、240（共6个）" → "90,120,…240"
    if not keep_sep:
        s = s.replace(",", "")
    return s


def _clean_segment(seg: str):
    """剥离段落后缀的非数学字符（单位等）与不成对的括号，返回可求值片段或 None"""
    x = re.sub(r"[^0-9+\-*/().%]+$", "", seg)   # 剥单位："2000元"→"2000"
    if not x:
        return None
    # 不成对括号："2000(原式"→"2000"、"2000)"→"2000"；"2*(999+1)" 成对保留
    while x.endswith("(") or (x.endswith(")") and "(" not in x):
        x = x[:-1]
        x = re.sub(r"[^0-9+\-*/().%]+$", "", x)
        if not x:
            return None
    if x.endswith("%"):                      # "50%" → 50/100
        x = x[:-1] + "/100"
    return x


def eval_math(expr: str):
    """安全求值简单算术表达式（数字、+ - * /、括号、小数、百分号）。
    除零/非法表达式返回 None。"""
    s = _clean_segment(expr) if expr else None
    if not s:
        return None
    # 预检：只允许数学字符；内部百分号无法正确求值 → 非法
    if re.search(r"[^0-9+\-*/().]", s) or "%" in s:
        return None
    # 递归下降解析
    i = 0
    n = len(s)

    def peek() -> str:
        return s[i] if i < n else ""

    def parse_num():
        nonlocal i
        m = re.match(r"\d+(?:\.\d+)?", s[i:])
        if not m:
            return None
        i += len(m.group(0))
        return float(m.group(0))

    def parse_factor():
        nonlocal i
        c = peek()
        if c == "(":
            i += 1
            v = parse_expr()
            if v is None or peek() != ")":
                return None
            i += 1
            return v
        if c == "+":
            i += 1
            return parse_factor()
        if c == "-":
            i += 1
            v = parse_factor()
            return None if v is None else -v
        return parse_num()

    def parse_term():
        nonlocal i
        v = parse_factor()
        if v is None:
            return None
        while peek() in ("*", "/"):
            op = peek()
            i += 1
            r = parse_factor()
            if r is None:
                return None
            if op == "/" and r == 0:
                return None
            v = v * r if op == "*" else v / r
        return v

    def parse_expr():
        nonlocal i
        v = parse_term()
        if v is None:
            return None
        while peek() in ("+", "-"):
            op = peek()
            i += 1
            r = parse_term()
            if r is None:
                return None
            v = v + r if op == "+" else v - r
        return v

    try:
        v = parse_expr()
    except RecursionError:
        return None
    if v is None or i != n:
        return None
    return v


def _result_value(s: str):
    """答案的最终结果值：按 '=' 分段取最后一段求值（用户写的最终结果）；
    最后一段不可求值（如夹带文字）时取第一个可求值段。无 '=' 取整体。"""
    segs = s.split("=")
    last = eval_math(segs[-1])
    if last is not None:
        return last
    for seg in segs:
        v = eval_math(seg)
        if v is not None:
            return v
    return None


def _same_num(a, b) -> bool:
    return a is not None and b is not None and abs(a - b) < 1e-9


# 中文数字容差：孩子可能写「五」「二十五」而非阿拉伯数字（小学低年级常见）。
# 仅当整个答案由中文数字字符构成时转换，避免误伤含数字义的普通文字答案。
_CN_DIGITS = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
              "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_CN_UNITS = {"十": 10, "百": 100, "千": 1000}


def _cn_num_value(s: str):
    """纯中文数字串 → 整数（支持 零/两、十百千万）；含其它字符返回 None。

    例：五→5、十→10、二十五→25、一百零五→105、两万→20000。
    """
    if not s or any(ch not in "零〇一二三四五六七八九十百千万两" for ch in s):
        return None
    total = 0      # 已累计的大段（万）
    section = 0    # 当前万以内小节
    digit = 0
    for ch in s:
        if ch == "万":
            section = (section + (digit or 0)) * 10000
            total += section
            section, digit = 0, 0
        elif ch in _CN_DIGITS:
            digit = _CN_DIGITS[ch]
        else:  # 十百千
            u = _CN_UNITS[ch]
            section += (digit if digit else 1) * u
            digit = 0
    return total + section + digit


def fill_answer_correct(user_ans, correct_ans) -> bool:
    """填空题容错判题（与前端 _matchAnswer 一致）"""
    u = normalize_answer(user_ans)
    a = normalize_answer(correct_ans)
    if not a:
        return False
    if u == a:
        return True
    if not re.search(r"\d", a):   # 正确答案无数字（单词/古诗文/句子）→ 严格
        return False

    # a) 最终结果求值比对：用户最后一段（陈述的结果）≈ 正确答案结果 → 对
    u_res = _result_value(u)
    a_res = _result_value(a)
    if _same_num(u_res, a_res):
        return True
    # a2) 中文数字容差：用户写「五」「二十五」等（纯中文数字），参考答案为数值 → 等价
    u_cn = _cn_num_value(u)
    if u_cn is not None and a_res is not None and _same_num(float(u_cn), a_res):
        return True

    # b) 数字 token 兜底：正确答案仅 1 个数字 → 用户答案最后一个数字须等于它；
    #    双方数字 token 完全一致（排序后数值比对，忽略书写顺序与分隔符写法）→ 对
    #    token 从保留分隔符的规范化串提取："90、120、150" 与 "90,120,150" 均为 3 个 token
    u_sep = normalize_answer(user_ans, keep_sep=True)
    a_sep = normalize_answer(correct_ans, keep_sep=True)
    u_nums = re.findall(r"-?\d+\.?\d*", u_sep)
    a_nums = re.findall(r"-?\d+\.?\d*", a_sep)
    if len(a_nums) == 1 and u_nums:
        try:
            if abs(float(u_nums[-1]) - float(a_nums[0])) < 1e-9:
                return True
        except ValueError:
            pass
    # 双方数字 token 数量一致 → 排序后逐一比对（忽略书写顺序："210,240,90…" 也算对）
    if u_nums and len(u_nums) == len(a_nums):
        try:
            us = sorted(float(x) for x in u_nums)
            as_ = sorted(float(y) for y in a_nums)
        except ValueError:
            us = as_ = None
        if us is not None and all(abs(x - y) < 1e-9 for x, y in zip(us, as_)):
            return True
    return False
