"""商品 / 分类 / 品牌排行分析（Phase 5）。

对应开发文档第 18 节：
- 商品排行：PV/Click/Collect/Cart/Buy/GMV/Unique Users/Conversion Rate，输出 TOP N；
- 分类排行：按分类统计用户数/PV/点击/收藏/加购/购买/订单/GMV/转化率；
- 品牌排行：按品牌统计销量/GMV/用户数/复购用户/客单价。
"""

from .ranking import brand_ranking, category_ranking, item_ranking

__all__ = ["item_ranking", "category_ranking", "brand_ranking"]
