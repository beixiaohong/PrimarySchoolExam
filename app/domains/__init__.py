"""域层（S1-R 模块化单体）：九域目录，每域 routers/ + services/ + contracts.py。

纪律：跨域访问只能经目标域 contracts.py；共享内核（database/config/models/schemas/
migrations）留在 app/ 根，不在域内复制。详见 docs/enterprise/02-模块拆分与开发方案.md。
"""
