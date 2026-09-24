"""等级配置模型（新功能 C 等级/成长体系，2026Q4）

`level_config` 是等级体系的**单一真相源**：每级的经验门槛、称号、特权描述与升级奖励
集中在此表，`services/level.py` 的 `level_for_exp()` / `get_level_info()` 均由其派生；
「是否达到某级」与「距离下一级还差多少经验」不再各自写一遍阈值，避免两处漂移。

- 表结构由迁移 `080_user_level.py` 幂等建立并 seed 默认 20 级（按 lv 增量补齐）；
- 服务层保留 `LEVEL_FALLBACK` 常量作为「表为空/表缺失」时的兜底（与 seed 内容一致，
  避免启动顺序或首次部署时等级阶梯为空导致进度条除零）；
- `reward_diamond` 是**真实发放**的升级奖励（经 `commerce.contracts.DiamondService.grant`），
  不是展示字段。

注意：MySQL 的 TEXT/MEDIUMTEXT 列不允许 DEFAULT，本表全部为 INT/VARCHAR/BOOL，可安全给默认值。
"""
from sqlalchemy import Boolean, Column, Integer, String

from ..database import Base


class LevelConfig(Base):
    """等级配置：一行一级，lv 为主键（1..20）"""
    __tablename__ = "level_config"
    __table_args__ = {"comment": "等级配置：每级经验门槛/称号/特权/升级奖励钻石"}

    lv = Column(Integer, primary_key=True, comment="等级（1-20，主键）")
    min_exp = Column(Integer, nullable=False, default=0,
                     comment="达到该等级所需累计经验（Lv1 固定为 0）")
    title = Column(String(32), nullable=False, default="",
                   comment="等级称号（如「勤学小芽」）")
    perk = Column(String(200), nullable=False, default="",
                  comment="该等级特权说明（展示用文案，头像框/展示位由前端按 lv 渲染）")
    reward_diamond = Column(Integer, nullable=False, default=0,
                            comment="升到该等级的一次性奖励钻石（真实发放）")
    is_active = Column(Boolean, nullable=False, default=True,
                       comment="是否启用；停用后该级不参与阶梯（用于后台临时下线某级权益）")

    def __repr__(self):
        return f"<LevelConfig Lv{self.lv} exp>={self.min_exp} {self.title}>"
