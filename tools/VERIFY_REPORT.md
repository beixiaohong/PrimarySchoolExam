# 数学题生成器答案验证报告

> 生成日期：2026-08-14
> 验证脚本：`tools/verify_math_answers.py`
> 原始数据：`tools/verify_math_report.txt`
> 验证范围：全部 **53** 个数学题生成器（`@register("code")`）

## 一、验证方法

- 跨 `difficulty ∈ {1..5}`、`grade ∈ {1..9}`，每组合迭代 **10** 次，单生成器约 450 题。
- 每道题生成用**守护线程包裹 + 超时（默认 2s）**：超时即记为 `HANG(疑似死循环)`，防止死循环拖垮整轮。
- 检测项：
  - 答案为 `None` / 空串 / 含字面 `None`；
  - 畸形代数式（`x²0x`、`x²+bx0`、`y=kx0`、`+0=`）正则匹配；
  - `number_large` 四舍五入与「四舍五入（round-half-up）」不一致；
  - `app_cow_grazing` 题设能否用统一 `(r, G)` 解释（自洽性）。
- 误报处理：首次 2s 超时把 `geo_area_plane` / `geo_volume` 标为 HANG，但二者均调用 `matplotlib` 渲染配图，冷启动首图渲染偏慢；改用 **60s** 超时复测后均通过，判定为**误报**（非数学 bug）。

## 二、总览

| 生成器 | 运行 | 缺陷 | 状态 |
|---|---|---|---|
| app_cow_grazing | 450 | 170 (37.8%) | ❌ Bug5 题设不自洽 |
| app_travel | 362 | 7 (1.9%) | ❌ Bug6 除零 + Bug7 死循环 |
| calc_equation | 450 | 23 (5.1%) | ❌ Bug1 答案为 None |
| mid_quadratic_eq | 450 | 25 (5.6%) | ❌ Bug3 畸形式 |
| mid_linear_func | 450 | 4 (0.9%) | ❌ Bug4 畸形式 |
| logic_reasoning | — | HANG | ❌ Bug10 死循环 |
| number_large | 450 | 0(随机) | ⚠️ Bug2 银行家舍入（源码确认，随机采样低频） |
| geo_area_plane | 135(60s复测) | 0 | ✅ 误报（matplotlib 冷启动） |
| geo_volume | 135(60s复测) | 0 | ✅ 误报（matplotlib 冷启动） |
| 其余 44 个生成器 | 450×44 | 0 | ✅ 无缺陷 |

## 三、已确认缺陷（8 个真实 bug）

### Bug1 · `calc_equation._eq_word_hard` — 答案恒为 None（严重）
- **现象**：难度较高的「列方程」题 23/450 (5.1%) 返回 `A: None`。
- **位置**：`app/services/math_generator/calc.py` 约 578–597 行。
- **根因**：函数提前 `return (question, None)`，下方用 `extra=random.randint(10,20)`、`back_speed=speed+extra`、`back_time=dist/back_speed` 重算正确答案的分支为**死代码**。
- **影响**：该类题无答案，前端无法判分。
- **修复方向**：删除提前 return，走到正确重算分支并 `return (question, 正确值)`。

### Bug2 · `number_large` — 四舍五入用银行家舍入（中）
- **现象**：`把 n 四舍五入到万/亿位` 用 `round(n/10000)` / `round(n/100000000)`。
- **位置**：`app/services/math_generator/number.py` 约 236–242 行。
- **根因**：Python `round()` 为「银行家舍入（round-half-to-even）」，与学校「四舍五入（round-half-up）」在余数为 `5000`(万)/`50000000`(亿) 时结果不同（如 25000→银行家 2、学校 3）。随机采样命中边界概率极低，故报告 0 缺陷，但属**确定性错误**，需修。
- **修复方向**：改用 `(n + unit//2)//unit`（整数 round-half-up）。

### Bug3 · `mid_quadratic_eq.variant_solve` — 畸形方程式（中）
- **现象**：`解方程: x²+bx0=0`（c==0）与 `x²0x-25=0`（b==0），25/450 (5.6%，17+8)。
- **位置**：`app/services/math_generator/middle.py` 约 22–37 行。
- **根因**：`f"解方程: x²{b_str}x{c_str}=0"`，b==0 得 `x²0x…`、c==0 得 `x²+bx0=0`；同时答案却给出正确根，题面与答案不一致。
- **修复方向**：b==0 时省略 `0x` 项、c==0 时省略 `+0` 项（或显式写 `x²+bx=0` / `x²+c=0`）。

### Bug4 · `mid_linear_func.variant_find_expr` — 畸形解析式（中）
- **现象**：`y=-4x0` / `y=5x0`（b==0），4/450 (0.9%)。
- **位置**：`app/services/math_generator/middle.py` 约 69–82 行。
- **根因**：`return q, f"y={k}x{b_str}"`，b==0 得 `y=kx0`（应为 `y=kx`）。
- **修复方向**：b==0 时省略 `+0` 项。

### Bug5 · `app_cow_grazing` — 题设不自洽（严重，高频）
- **现象**：34.4%–37.8% 题设无法用统一 `(r, G)` 解释，答案错误，如「11头牛6天吃完，24头牛几天吃完？→2天」。
- **位置**：`app/services/math_generator/app.py` 约 564–610 行。
- **根因**：`G = random.randint(80,150)` 是死变量从未使用；`actual_G = cows1*days1 - r*days1`；`days2 = actual_G // denom if actual_G % denom == 0 else actual_G // denom`（非整除时向下取整，与「匀速生长」矛盾）。
- **影响**：约 1/3 的牛吃草题答案错误。
- **修复方向**：先由 `(cows1, days1)` 与 `(cows2, days2)` 反解统一 `(r, G)`（须整除且为正），再据第三问求天数；凑不出合法参数则重抽。

### Bug6 · `app_travel` 追及变体 — 除零崩溃（严重）
- **现象**：难度 3–4 追及变体在 `v1==v2` 时抛 `ZeroDivisionError`（6 次 EXCEPTION）。
- **位置**：`app/services/math_generator/app.py` 第 33 行 `f"…甲在乙后{dist//t*(v1-v2)//(v1-v2)}千米…"` 及第 38 行 `gap // (v1 - v2)`。
- **根因**：`v1==v2` 时 `(v1-v2)=0` 触发除零；该变体本就返回 `None` 为死路径。
- **修复方向**：`v1, v2` 保证 `v1 != v2`（追及场景本就不可能同速），或在构造前特判。

### Bug7 · `app_travel` 环形跑道 — 死循环（严重）
- **现象**：难度 ≥5 `_travel_circular` 在部分参数下**进程挂起**（HANG，实测 d5 起必现）。
- **位置**：`app/services/math_generator/app.py` 第 60–66 行 `while circumference % (v1 + v2) != 0: circumference += 10`。
- **根因**：当 `gcd(10, v1+v2)` 不整除起始 `circumference`（如 `v1+v2` 为 10 的倍数而 `circumference` 非 10 的倍数），`+=10` 序列永远碰不到 `(v1+v2)` 的倍数 → 死循环。
- **修复方向**：`circumference` 初始化为 `((random.randint(20,60) * (v1+v2) + (v1+v2)-1) // (v1+v2)) * (v1+v2)` 或直接在 `while` 中按 `(v1+v2)` 向上取整。

### Bug10 · `logic_reasoning` 鸡兔同笼 — 死循环（严重）
- **现象**：难度 3–4 分支在部分参数下**进程挂起**（HANG，60s 复测仍挂，实测 d3 g9）。
- **位置**：`app/services/math_generator/logic.py` 第 29–33 行 `while (legs - 2*heads) % 2 != 0 or legs > heads*4: legs += 1`。
- **根因**：当随机 `legs` 已大于 `heads*4`（heads∈[15,19] 时可能），`legs += 1` 只会让 `legs` 更大，`legs > heads*4` 恒真 → 死循环。
- **修复方向**：循环只修正奇偶性；若 `legs > heads*4` 或 `legs < 2*heads` 则重新生成 `legs`（限制在 `[2*heads+2, 4*heads-2]` 的偶数内）。

## 四、误报（已排除，非 bug）

- `geo_area_plane`、`geo_volume`：首次 2s 超时误判为死循环，实为 `matplotlib` 配图渲染冷启动慢；60s 超时复测 **135 题全通过**，判定误报。

## 五、结论与修复优先级

| 优先级 | Bug | 类型 |
|---|---|---|
| P0（答案错/崩溃/死循环） | Bug1, Bug5, Bug6, Bug7, Bug10 | 答案缺失 / 错误 / 进程挂起 |
| P1（题面畸形） | Bug3, Bug4 | 题面与答案不一致 |
| P2（低频确定性错） | Bug2 | 边界四舍五入 |

**建议**：先修 P0（影响作答与系统稳定性），再修 P1/P2，并补充 `tests/test_math_answers.py` 回归测试（针对每个 bug 的固定用例 + 全量随机重跑无 HANG/无 None/无畸形式）。

---
*本报告依据「先出验证报告再修」的流程产出，供确认后实施修复。*
