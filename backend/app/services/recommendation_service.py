"""推荐服务：单算法推荐 / 多算法对比 / 推荐评估。

遵循开发文档：
- 统一 recommend(user_id, top_k) 接口（第 35 节）；
- 过滤已购买/下架/不存在/重复（第 35.7 节）；
- 每条推荐尽量提供 reason（第 35.8 节）；
- API 只加载离线模型，禁止请求时重训（第 46 节）。
"""

from __future__ import annotations

from ..core.exceptions import ValidationError
from ..repositories import model_repo, recommendation_repo
from ..repositories.base import RECOMMEND_ALGORITHMS


def recommend(user_id: str, algorithm: str = "popular", top_k: int = 10) -> dict:
    """对某用户用指定算法返回 Top-K 推荐。"""
    top_k = _clamp_top_k(top_k)
    model = recommendation_repo.get_recommender(algorithm)
    items = model.recommend(str(user_id), top_k=top_k)
    return {
        "user_id": str(user_id),
        "algorithm": str(algorithm).lower(),
        "top_k": top_k,
        "count": len(items),
        "items": items,
    }


def compare(user_id: str, algorithms: list[str] | None = None, top_k: int = 10) -> dict:
    """多算法对比：同一用户下各算法推荐结果与命中商品。"""
    top_k = _clamp_top_k(top_k)
    algos = algorithms or list(RECOMMEND_ALGORITHMS)
    results: dict[str, dict] = {}
    for alg in algos:
        try:
            results[alg] = recommend(user_id, algorithm=alg, top_k=top_k)
        except ValidationError:
            raise
        except Exception as exc:  # 单个算法失败不影响整体对比
            results[alg] = {"user_id": str(user_id), "algorithm": alg, "top_k": top_k, "count": 0, "items": [], "error": str(exc)}
    return {
        "user_id": str(user_id),
        "top_k": top_k,
        "algorithms": list(results.keys()),
        "results": results,
    }


def metrics() -> dict:
    """推荐评估 + 权重实验结论（基于离线指标，不主观声称）。"""
    ev = model_repo.evaluation_summary()
    rows = sorted(
        (
            {
                "algorithm": alg,
                "precision@k": m.get("precision@k"),
                "recall@k": m.get("recall@k"),
                "f1@k": m.get("f1@k"),
                "hit_rate@k": m.get("hit_rate@k"),
                "ndcg@k": m.get("ndcg@k"),
                "coverage@k": m.get("coverage@k"),
            }
            for alg, m in (ev.get("results") or {}).items()
        ),
        key=lambda r: -(r.get("ndcg@k") or 0),
    )
    wexp = {}
    try:
        wexp = model_repo.weight_experiment()
    except Exception:
        pass
    return {
        "method": ev.get("method"),
        "k": ev.get("k"),
        "test_ratio": ev.get("test_ratio"),
        "max_users": ev.get("max_users"),
        "baseline": ev.get("baseline"),
        "conclusion": ev.get("conclusion"),
        "algorithms": rows,
        "weight_experiment": {
            "best_experiment": wexp.get("best_experiment"),
            "best_weights": wexp.get("best_weights"),
            "selection_criterion": wexp.get("selection_criterion"),
            "note": wexp.get("note"),
        },
    }


def _clamp_top_k(top_k: int) -> int:
    if top_k < 1 or top_k > 50:
        raise ValidationError(message="top_k 需在 1~50 之间")
    return top_k