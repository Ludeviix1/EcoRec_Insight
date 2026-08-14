"""推荐离线评估 + 权重实验（Phase 12，开发文档第 49.10 节 / 36 节）。

权重不能硬编码在业务逻辑中：至少进行一次权重实验（实验A 1/2/3/4/5、实验B
1/2/4/6/8、实验C 1/2/3/5/10），通过离线时间切分评估
（Precision@K / Recall@K / F1@K / HitRate@K / NDCG@K / Coverage），
最终选择依据必须来自离线实验，而不是"感觉这个权重更合理"。

离线评估原则（开发文档第 36 节）：历史行为 → train，未来行为 → test；
推荐只能使用 train 信息，test 只用于评价。
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from .base import BaseRecommender
from .config import RecommendConfig, load_recommend_config
from .popular import PopularRecommender

# 官方权重实验（开发文档第 49.10 节）
WEIGHT_VARIANTS: list[dict[str, float]] = [
    {"name": "A_1_2_3_4_5", "pv": 1.0, "click": 2.0, "collect": 3.0, "cart": 4.0, "buy": 5.0},
    {"name": "B_1_2_4_6_8", "pv": 1.0, "click": 2.0, "collect": 4.0, "cart": 6.0, "buy": 8.0},
    {"name": "C_1_2_3_5_10", "pv": 1.0, "click": 2.0, "collect": 3.0, "cart": 5.0, "buy": 10.0},
]

DEFAULT_EVAL_K = 10
DEFAULT_TEST_RATIO = 0.25       # 未来 25% 行为作为测试集
DEFAULT_MAX_USERS = 3000        # 评估用户数上限（保证离线实验可复现且不发散）


def split_train_test(behaviors: pd.DataFrame, test_ratio: float = DEFAULT_TEST_RATIO,
                     ref_date: pd.Timestamp | None = None) -> tuple[pd.DataFrame, pd.DataFrame, pd.Timestamp]:
    """严格时间切分：历史行为 → train，未来行为 → test。

    - 以行为事件日期为时间线，取最晚 ref_date 前 test_ratio 比例的时间窗作为 test；
    - 推荐模型只允许看到 train，test 仅用于评价；
    - 保证切分日期落在行为日期范围内（至少留 1 天给 train）。
    """
    dates = pd.to_datetime(behaviors["event_date"], errors="coerce").dt.normalize()
    max_date = ref_date or dates.max()
    max_date = pd.Timestamp(max_date).normalize()
    min_date = dates.min()

    span = (max_date - min_date).days
    test_days = max(1, int(round(span * test_ratio)))
    cut_date = max_date - pd.Timedelta(days=test_days)
    if cut_date <= min_date:          # 极端小数据：至少保留 2 天
        cut_date = min_date + pd.Timedelta(days=1)

    test_mask = dates > cut_date
    train = behaviors[~test_mask].copy()
    test = behaviors[test_mask].copy()
    return train, test, cut_date


def _user_test_targets(test: pd.DataFrame) -> dict[str, set[str]]:
    """每个用户在测试期真正交互过的商品集合（ground truth）。"""
    out: dict[str, set[str]] = {}
    for uid, g in test.groupby("user_id"):
        out[str(uid)] = set(g["item_id"].astype(str))
    return out


def _dcg(relevances: list[float], k: int) -> float:
    return sum(r / math.log2(i + 2) for i, r in enumerate(relevances[:k]))


def _ndcg(rec: list[str], rel: set[str], k: int) -> float:
    graded = [1.0 if it in rel else 0.0 for it in rec[:k]]
    dcg = _dcg(graded, k)
    ideal = _dcg([1.0] * min(len(rel), k), k)
    if ideal <= 0:
        return 0.0
    return dcg / ideal


def metrics_at_k(rec: list[str], rel: set[str], k: int) -> dict:
    """单用户 Top-K 评估指标。rec 为排序后的推荐商品列表（长度不限，取前 k）。"""
    top = rec[:k]
    hits = len([it for it in top if it in rel])
    top_k = max(1, k) if k >= 1 else 1
    precision = hits / top_k
    recall = hits / len(rel) if rel else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    hit_rate = 1.0 if hits > 0 else 0.0
    ndcg = _ndcg(rec, rel, k)
    return {
        "precision@k": round(precision, 6),
        "recall@k": round(recall, 6),
        "f1@k": round(f1, 6),
        "hit_rate@k": round(hit_rate, 6),
        "ndcg@k": round(ndcg, 6),
    }


def coverage(recommended_items: set[str], candidate_items: pd.Index) -> float:
    """Coverage：推荐列表中出现的不同商品数 / 候选商品总数（全局指标）。"""
    total = len(candidate_items)
    if total == 0:
        return 0.0
    unique_rec = len(recommended_items & set(candidate_items))
    return unique_rec / total


def evaluate_popular(model: BaseRecommender, train: pd.DataFrame, test: pd.DataFrame,
                     items: pd.DataFrame, k: int = DEFAULT_EVAL_K,
                     max_users: int = DEFAULT_MAX_USERS) -> dict:
    """在时间切分上评估已训练好的推荐模型。

    用 train 期行为过滤候选（不能把 test 中才有的商品当作 ground truth），
    对每个测试期活跃用户生成 Top-K 推荐并与真实交互对比。
    返回各用户指标的均值 + 全局 Coverage。
    """
    targets = _user_test_targets(test)
    users = list(targets.keys())
    if max_users is not None:
        users = users[:max_users]

    per_user = []
    rec_items: set[str] = set()
    for uid in users:
        rel = targets[uid]
        recs = model.recommend(uid, top_k=k)
        rec_ids = [r["item_id"] for r in recs]
        top = rec_ids[:k]
        per_user.append(metrics_at_k(top, rel, k))
        rec_items.update(top)

    if not per_user:
        m = {"precision@k": 0.0, "recall@k": 0.0, "f1@k": 0.0, "hit_rate@k": 0.0, "ndcg@k": 0.0}
    else:
        df = pd.DataFrame(per_user)
        m = {c: round(float(df[c].mean()), 4) for c in per_user[0]}

    cand_items = pd.Series(index=items["item_id"].astype(str))
    m["coverage@k"] = round(coverage(rec_items, cand_items.index), 4)
    m["n_users"] = len(users)
    return m


def run_weight_experiment(behaviors: pd.DataFrame, items: pd.DataFrame,
                          orders: pd.DataFrame | None = None,
                          order_items: pd.DataFrame | None = None,
                          cfg: RecommendConfig | None = None,
                          k: int = DEFAULT_EVAL_K,
                          test_ratio: float = DEFAULT_TEST_RATIO,
                          max_users: int = DEFAULT_MAX_USERS,
                          ) -> tuple[pd.DataFrame, dict[str, dict]]:
    """离线权重实验：对每个候选权重集在时间切分上评估，返回对比表与明细。

    返回:
        summary: DataFrame，每行一个实验（含各 @K 指标均值）
        details: {实验名: 指标明细}，供落盘 / 展示
    """
    cfg = cfg or load_recommend_config()
    train, test, cut_date = split_train_test(behaviors, test_ratio)

    rows: list[dict] = []
    details: dict[str, dict] = {}
    for variant in WEIGHT_VARIANTS:
        weights = {bt: variant[bt] for bt in ("pv", "click", "collect", "cart", "buy")}
        vcfg = RecommendConfig(
            processed_dir=cfg.processed_dir,
            interim_dir=cfg.interim_dir,
            output_dir=cfg.output_dir,
            behavior_weights=weights,
            half_life_days=cfg.half_life_days,
            as_of_date=str(cut_date),           # 训练只用截至 cut_date 的数据
            top_k=k,
            filter_purchased=cfg.filter_purchased,
            filter_off_shelf=cfg.filter_off_shelf,
        )
        model = PopularRecommender(vcfg).fit(train, items, orders, order_items, ref_date=cut_date)
        met = evaluate_popular(model, train, test, items, k=k, max_users=max_users)
        row = {"experiment": variant["name"]}
        row.update({bt: weights[bt] for bt in ("pv", "click", "collect", "cart", "buy")})
        row.update(met)
        rows.append(row)
        details[variant["name"]] = dict(met)

    summary = pd.DataFrame(rows).sort_values("ndcg@k", ascending=False).reset_index(drop=True)
    summary["rank"] = range(1, len(summary) + 1)
    return summary, details


def choose_best(summary: pd.DataFrame) -> str:
    """依据离线实验选择最优权重：按 NDCG@10 排序（并列时按 Recall@10）。"""
    s = summary.sort_values(["ndcg@k", "recall@k"], ascending=False)
    return str(s.iloc[0]["experiment"])


def compare_algorithms(behaviors: pd.DataFrame, items: pd.DataFrame,
                       orders: pd.DataFrame | None = None,
                       order_items: pd.DataFrame | None = None,
                       cfg: RecommendConfig | None = None,
                       algorithms: list[str] | None = None,
                       k: int = DEFAULT_EVAL_K,
                       test_ratio: float = DEFAULT_TEST_RATIO,
                       max_users: int = DEFAULT_MAX_USERS,
                       ) -> tuple[pd.DataFrame, dict[str, dict]]:
    """离线对比多个推荐算法（开发文档第 36 节，Phase 14/15 共用）。

    严格时间切分：历史 → train，未来 → test；推荐只用 train 信息。
    对比指标：Precision@K / Recall@K / F1@K / HitRate@K / NDCG@K / Coverage。

    参数:
        algorithms: 参与对比的算法名，取值 popular / itemcf / usercf / content / hybrid，
                    默认全部。
    返回:
        (summary, details) 与 run_weight_experiment 结构一致。
    """
    from .content import ContentRecommender
    from .hybrid import HybridRecommender
    from .itemcf import ItemCFRecommender
    from .popular import PopularRecommender
    from .usercf import UserCFRecommender

    algos = algorithms or ["popular", "itemcf", "usercf", "content", "hybrid"]
    cfg = cfg or load_recommend_config()
    train, test, cut_date = split_train_test(behaviors, test_ratio)

    factories: dict[str, tuple[type, dict]] = {
        "popular": (PopularRecommender, {}),
        "itemcf": (ItemCFRecommender, {}),
        "usercf": (UserCFRecommender, {"n_neighbors": cfg.n_neighbors}),
        "content": (ContentRecommender, {}),
        "hybrid": (HybridRecommender, {"hybrid_weights": cfg.hybrid_weights, "n_neighbors": cfg.n_neighbors}),
    }

    rows: list[dict] = []
    details: dict[str, dict] = {}
    for name in algos:
        if name not in factories:
            continue
        cls, kwargs = factories[name]
        model = cls(cfg, **kwargs).fit(train, items, orders, order_items, ref_date=cut_date)
        met = evaluate_popular(model, train, test, items, k=k, max_users=max_users)
        rows.append({"algorithm": name, **met})
        details[name] = dict(met)

    summary = pd.DataFrame(rows).sort_values("ndcg@k", ascending=False).reset_index(drop=True)
    summary["rank"] = range(1, len(summary) + 1)
    return summary, details


def report_table(summary: pd.DataFrame, k: int = DEFAULT_EVAL_K) -> pd.DataFrame:
    """把 compare_algorithms 的表整理成开发文档规定的输出列（Phase 15 第 49.13 节）。

    Algorithm / Precision@10 / Recall@10 / F1@10 / HitRate@10 / NDCG@10 / Coverage
    """
    if summary.empty:
        return summary.copy()
    ren = {
        "algorithm": "Algorithm",
        "precision@k": f"Precision@{k}",
        "recall@k": f"Recall@{k}",
        "f1@k": f"F1@{k}",
        "hit_rate@k": f"HitRate@{k}",
        "ndcg@k": f"NDCG@{k}",
        "coverage@k": "Coverage",
    }
    cols = [c for c in ("algorithm", "precision@k", "recall@k", "f1@k",
                        "hit_rate@k", "ndcg@k", "coverage@k") if c in summary.columns]
    return summary[cols].rename(columns=ren).copy()


def conclude_vs_baseline(details: dict[str, dict], k: int = DEFAULT_EVAL_K,
                         baseline: str = "popular") -> str:
    """依据离线指标给出诚实结论（Phase 15：候选未优于 baseline 时禁止声称更好）。

    判定：候选算法 NDCG@{k} 必须严格高于 baseline 才算更优；否则不声称更好。
    """
    base = details.get(baseline, {}) or {}
    cand = [n for n in details if n != baseline and details[n]]
    if not cand:
        return f"无 {baseline} 之外的候选算法可对比（基于离线指标）"
    top = max(cand, key=lambda n: (details[n] or {}).get("ndcg@k", 0.0))
    b_ndcg = base.get("ndcg@k") or 0.0
    t_ndcg = (details[top] or {}).get("ndcg@k") or 0.0
    if t_ndcg > b_ndcg:
        return (f"{top} NDCG@{k}={t_ndcg} vs {baseline}={b_ndcg} → "
                f"{top} 更优（基于离线指标）")
    return (f"最高候选 {top} NDCG@{k}={t_ndcg} 未严格高于 {baseline}={b_ndcg}，"
            f"不强行声称混合更好（基于离线指标）")