"""请求日志中间件：记录每个 API 请求的方法、路径、状态码、耗时。

示例日志：INFO  api.request | GET /api/health status=200 latency=1.2ms
满足开发文档第 44 节"日志"要求中的 API request / latency 记录。
"""

import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from ..core.logging import get_logger

logger = get_logger("api.request")


class RequestLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        latency_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "%s %s status=%s latency=%.1fms",
            request.method,
            request.url.path,
            response.status_code,
            latency_ms,
        )
        return response