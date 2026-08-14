"""业务发现（开发文档第 49.5 节）。

把各分析结果升级为可解释的业务结论，统一结构：

    现象 → 证据 → 可能原因 → 业务建议

输入：run_analysis 输出的 results dict（各分析 JSON）。
输出：按领域组织的 findings 列表。

重要声明：数据为模拟数据，原因与建议仅是方法论演示，
不得表述为真实电商业务结论。
"""

from __future__ import annotations

import pandas as pd

_DISCLAIMER = "数据为模拟数据，原因和建议是方法论演示，不得表述为真实电商业务结论。"


def build_findings(results: dict) -> dict:
    """根据全量分析结果生成业务发现。

    参数:
        results: run_analysis 的返回 dict（键=分析名，值为 analysis JSON）

    返回:
        dict:
        - disclaimer: 模拟数据声明
        - domains: list[{"domain","title","findings":[{现象, 证据, 可能原因, 业务建议}]}]
    """
    domains: list[dict] = []

    # ---- 用户规模 / 活跃 ----
    domains.append(_user_scale(results))
    domains.append(_behavior_funnel(results))
    domains.append(_retention(results))
    domains.append(_cohort(results))
    domains.append(_rfm(results))
    domains.append(_lifecycle(results))
    domains.append(_path(results))
    domains.append(_item_ranking(results))
    domains.append(_item_life(results))
    domains.append(_price(results))
    domains.append(_channel(results))
    domains.append(_device(results))
    domains.append(_association(results))
    domains.append(_segmentation(results))

    domains = [d for d in domains if d is not None]
    return {"disclaimer": _DISCLAIMER, "total_domains": len(domains), "domains": domains}


# ----------------------------------------------------------------------
# 各领域发现生成
# ----------------------------------------------------------------------
def _finding(domain: str, title: str, findings: list) -> dict:
    return {"domain": domain, "title": title, "findings": findings}


def _gen(现象: str, 证据: str | list, 可能原因: str, 业务建议: str) -> dict:
    if isinstance(证据, list):
        evidence = 证据
    else:
        evidence = [证据]
    return {
        "现象": 现象,
        "证据": evidence,
        "可能原因": 可能原因,
        "业务建议": 业务建议,
    }


def _user_scale(r: dict) -> dict | None:
    d = r.get("user_scale") or {}
    if not d:
        return None
    total, active = d.get("total_users", 0), d.get("active_users", 0)
    pay = d.get("pay_rate", 0.0)
    findings = [
        _gen(
            f"活跃用户占比高（{active}/{total}），但付费率仅 {pay:.1%}",
            f"active_users={active}, total_users={total}, pay_rate={pay}",
            "浏览-购买转化漏斗在点击/加购环节流失较大",
            "针对未付费活跃用户做加购/收藏行为驱动转化，如优惠券与加购提醒",
        )
    ]
    return _finding("user_scale", "用户规模", findings)


def _behavior_funnel(r: dict) -> dict | None:
    d = r.get("funnel") or {}
    if not d:
        return None
    steps = d.get("steps", [])
    if not steps:
        return None
    drop = []
    for i in range(1, len(steps)):
        prev, cur = steps[i - 1], steps[i]
        drop.append(f"{prev['stage']}->{cur['stage']}: {cur['step_conversion_rate']:.1%}")
    findings = [
        _gen(
            "转化漏斗逐步衰减，" + "，".join(drop),
            [f"{s['stage']}: {s.get('count', 0)} (rate={s.get('step_conversion_rate', 0):.1%})" for s in steps],
            "各环节用户流失由兴趣衰减/决策犹豫/支付门槛等原因导致",
            "对高流失环节（如 cart->buy）优化支付体验与优惠激励",
        )
    ]
    return _finding("funnel", "转化漏斗", findings)


def _retention(r: dict) -> dict | None:
    d = r.get("retention") or {}
    if not d:
        return None
    overall = d.get("overall", [])
    if not overall:
        return None
    evidence = [f"{o['label']}: {o['rate']:.1%} (retained {o['retained']}/{o['base']})" for o in overall]
    first = overall[0]
    findings = [
        _gen(
            f"次日留存率约 {first['rate']:.1%}，随天数衰减",
            evidence,
            "首次体验价值不足或缺少回访动机",
            "优化新用户首次体验、推送个性化回访内容",
        )
    ]
    return _finding("retention", "留存", findings)


def _cohort(r: dict) -> dict | None:
    d = r.get("cohort") or {}
    if not d:
        return None
    n = d.get("total_cohorts", 0)
    agg = d.get("aggregate", {})
    ev = {f"day_{k}": agg.get(f"day_{k}") for k in (1, 7, 30)}
    findings = [
        _gen(
            f"共 {n} 个 Cohort，聚合留存率呈健康衰减",
            f"aggregate={ {k: (round(v, 4) if v is not None else None) for k, v in ev.items()} }",
            "不同注册期用户行为质量存在差异",
            "对高留存 Cohort 归纳共性，用于投放与运营复制",
        )
    ]
    return _finding("cohort", "Cohort 留存", findings)


def _rfm(r: dict) -> dict | None:
    d = r.get("rfm") or {}
    if not d:
        return None
    seg = {s["segment"]: s for s in d.get("segment_distribution", [])}
    if not seg:
        return None
    high = seg.get("高价值", {})
    risk = seg.get("流失风险", {})
    evidence = [f"{s['segment']}: {s['count']} 人, GMV {s['gmv']}" for s in d["segment_distribution"]]
    findings = [
        _gen(
            f"高价值用户 {high.get('count', 0)} 人、流失风险 {risk.get('count', 0)} 人",
            evidence,
            "用户价值分层明显，尾部用户活跃与消费均偏低",
            "对高价值用户做会员权益维护，对流失风险用户做唤醒召回",
        )
    ]
    return _finding("rfm", "RFM 分群", findings)


def _lifecycle(r: dict) -> dict | None:
    d = r.get("lifecycle") or {}
    if not d:
        return None
    dist = {s["stage"]: s for s in d.get("distribution", [])}
    if not dist:
        return None
    active = dist.get("活跃用户", {})
    risk = dist.get("流失风险", {})
    evidence = [f"{s['stage']}: {s['count']} 人 ({s['ratio']:.1%}), GMV {s['gmv']}" for s in d["distribution"]]
    findings = [
        _gen(
            f"活跃用户占比 {active.get('ratio', 0):.1%}，流失风险用户 {risk.get('count', 0)} 人需关注",
            evidence,
            "生命周期分布反映活跃与留存之间的平衡",
            "针对沉默/流失风险评估唤醒策略，对高价值用户强化关系经营",
        )
    ]
    return _finding("lifecycle", "用户生命周期", findings)


def _path(r: dict) -> dict | None:
    d = r.get("purchase_path") or {}
    if not d:
        return None
    top = d.get("top_paths", [])
    if not top:
        return None
    main = top[0]
    evidence = [
        f"{p['path']}: {p['sessions']} 会话 {p['users']} 用户, 购买率 {p['final_buy_rate']:.1%}"
        for p in top
    ]
    findings = [
        _gen(
            f"最常见路径为 {main['path']}（{main['sessions']} 会话）",
            evidence,
            "购买路径集中在少数典型链路",
            "针对高购买率路径优化页面串联，对低购买率路径减少环节",
        )
    ]
    return _finding("purchase_path", "购买路径", findings)


def _item_ranking(r: dict) -> dict | None:
    d = r.get("item_ranking") or {}
    if not d:
        return None
    items = d.get("items", [])
    if not items:
        return None
    top = items[0]
    evidence = [f"{i['item_name']}: PV {i['pv']}, BUY {i['buy']}, GMV {i['gmv']}" for i in items[:3]]
    findings = [
        _gen(
            f"头部商品 {top['item_name']} 贡献显著热门度与 GMV",
            evidence,
            "热门商品集中度高，呈现长尾效应",
            "保证头部商品库存供给，同时对潜力商品做流量扶持",
        )
    ]
    return _finding("item_ranking", "商品热门", findings)


def _item_life(r: dict) -> dict | None:
    d = r.get("item_lifecycle") or {}
    if not d:
        return None
    dist = {s["stage"]: s for s in d.get("distribution", [])}
    if not dist:
        return None
    boom = dist.get("爆款", {})
    new = dist.get("新品", {})
    evidence = [f"{s['stage']}: {s['count']} 件, GMV {s['total_gmv']}" for s in d["distribution"]]
    findings = [
        _gen(
            f"爆款商品 {boom.get('count', 0)} 件、新品 {new.get('count', 0)} 件",
            evidence,
            "商品生命周期分化，爆款与新品的运营策略应不同",
            "爆款保障库存与曝光，新品做冷启动与验证",
        )
    ]
    return _finding("item_lifecycle", "商品生命周期", findings)


def _price(r: dict) -> dict | None:
    d = r.get("price") or {}
    if not d:
        return None
    bins = d.get("price_bins", [])
    if not bins:
        return None
    best = max(bins, key=lambda b: b["buy_rate"])
    cross = d.get("cross", {})
    ev = [
        f"{b['bin_label']}: buy_rate {b['buy_rate']:.1%}, GMV {b['gmv']}, 频率 {b.get('buy_freq', 0)}"
        for b in bins[:3]
    ]
    findings = [
        _gen(
            f"价格带 {best['bin_label']} 购买率最高（{best['buy_rate']:.1%}）",
            ev + [f"correlation={cross}"],
            "价格带影响转化，不同价格段用户偏好不同",
            "在转化高的价格带加大选品，在转化低的带优化定价策略",
        )
    ]
    return _finding("price", "价格分析", findings)


def _channel(r: dict) -> dict | None:
    d = r.get("channel") or {}
    if not d:
        return None
    chs = d.get("channels", [])
    if not chs:
        return None
    best = max(chs, key=lambda c: c["buy_rate"])
    evidence = [
        f"{c['channel']}: 用户 {c['users']}, buy率 {c['buy_rate']:.1%}, GMV {c['gmv']}, AOV {c['aov']}"
        for c in chs
    ]
    findings = [
        _gen(
            f"渠道 {best['channel']} 购买率最高（{best['buy_rate']:.1%}）",
            evidence + [d.get("note", "")],
            "不同渠道流量质量存在明显差异",
            "加大高质量渠道投入，优化低质量渠道的页面与承接",
        )
    ]
    return _finding("channel", "渠道质量", findings)


def _device(r: dict) -> dict | None:
    d = r.get("device") or {}
    if not d:
        return None
    devs = d.get("devices", [])
    if not devs:
        return None
    mobile = next((x for x in devs if x["device"] == "mobile"), None)
    evidence = [
        f"{x['device']}: 用户 {x['users']}, buy率 {x['buy_rate']:.1%}, GMV {x['gmv']}, 晚间占比 {x['evening_ratio']:.1%}"
        for x in devs
    ]
    note = f"移动端用户占比 {mobile['users']}（行为占比 {mobile['behavior_ratio']:.1%}）" if mobile else ""
    findings = [
        _gen(
            note or "设备端指标差异明显",
            evidence,
            "移动端为主流渠道，转化与 GMV 占比高",
            "优先保障移动端体验与加载性能",
        )
    ]
    return _finding("device", "设备分析", findings)


def _association(r: dict) -> dict | None:
    d = r.get("association") or {}
    if not d:
        return None
    rules = d.get("item_rules", []) or d.get("category_rules", [])
    if not rules:
        return _finding("association", "关联规则", [
            _gen("未发现满足条件的强关联规则",
                 f"item_rules_count={d.get('item_rules_count', 0)}, "
                 f"category_rules_count={d.get('category_rules_count', 0)}, "
                 f"min_support={d.get('config', {}).get('min_support')}",
                 "购物篮多为单商品，或支持度阈值过高",
                 "可降低 min_support 或补充组合购买行为数据")
        ])
    top = rules[0]
    evidence = [
        f"{'→'.join(x['antecedents'])} => {'→'.join(x['consequents'])}  "
        f"support {x['support']}, conf {x['confidence']}, lift {x['lift']}"
        for x in rules[:3]
    ]
    findings = [
        _gen(
            f"最强规则：{'→'.join(top['antecedents'])} → {'→'.join(top['consequents'])}（lift={top['lift']}）",
            evidence,
            "商品/分类存在组合购买倾向，可由数据挖掘得到",
            "对高 lift 组合做捆绑推荐与搭配营销",
        )
    ]
    return _finding("association", "关联规则", findings)


def _segmentation(r: dict) -> dict | None:
    d = r.get("user_segments") or {}
    if not d:
        return None
    clusters = d.get("clusters", [])
    if not clusters:
        return None
    top = clusters[0]
    evidence = [
        f"簇{int(c['cluster_id']) + 1} {c['cluster_name']}: {c['size']}人 ({c['ratio']:.1%}) {c['interpretation']}"
        for c in clusters
    ]
    findings = [
        _gen(
            f"最大用户群为 {top['cluster_name']}（{top['size']}人，{top['ratio']:.1%}）",
            evidence,
            "用户按行为与消费特征自然聚类成不同价值群体",
            "按群差异化运营：高价值维护、潜力转化、沉默唤醒、流失召回",
        )
    ]
    return _finding("user_segments", "用户分群", findings)