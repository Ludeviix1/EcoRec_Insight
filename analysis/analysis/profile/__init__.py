"""派生分析层画像（开发文档第 5.1 / 23.1 节）。

- user_profile：每用户综合画像；
- item_profile：每商品综合画像。
"""

from .item_profile import ItemProfileConfig, item_profile
from .user_profile import ProfileConfig, user_profile

__all__ = ["ProfileConfig", "user_profile", "ItemProfileConfig", "item_profile"]