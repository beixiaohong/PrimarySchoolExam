"""契约层公共工具：延迟再导出（PEP 562 `__getattr__`）

各域 `contracts.py` 只登记「对外符号 → (实现模块, 实现属性)」映射，真正的 import 推迟到
首次属性访问时发生。这样契约层不会新增任何 import 期依赖：调用方 `from X.contracts import y`
的解析时机与改造前 `from X.impl import y` 完全一致（模块级调用点仍在 import 期解析、
函数级调用点仍在调用期解析），因此存量的跨域引用时序不变、不会出现「部分初始化模块」环。

映射值约定：
- `("app.domains.platform.services.ai", "chat")` → 再导出该模块的 `chat` 属性
- `("app.domains.platform.services.ai", None)`   → 再导出模块对象本身（供 `ai_svc.xxx` 调用点）
"""
import importlib


def resolve(exports, name):
    """按登记表解析对外符号；未登记的名字抛 AttributeError（保持 `from m import x` 的报错语义）"""
    if name not in exports:
        raise AttributeError("module has no attribute %r" % (name,))
    module_path, attr = exports[name]
    module = importlib.import_module(module_path)
    return module if attr is None else getattr(module, attr)
