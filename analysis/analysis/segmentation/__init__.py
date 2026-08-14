"""用户分群（开发文档第 23.2 节，KMeans 进阶）。"""

from .segmentation import CLUSTER_FEATURES, RANDOM_STATE, SegmentConfig, user_segmentation

__all__ = ["CLUSTER_FEATURES", "RANDOM_STATE", "SegmentConfig", "user_segmentation"]