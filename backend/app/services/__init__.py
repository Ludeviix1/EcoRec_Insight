"""服务层：业务编排（Route → Service → Repository → Database/Model）。"""

from . import (  # noqa: F401
    analysis_service,
    dashboard_service,
    item_service,
    prediction_service,
    recommendation_service,
    user_service,
)