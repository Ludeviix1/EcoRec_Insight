"""FastAPI 应用入口：装配中间件、路由、全局异常处理器。

统一响应格式：{"code": 0, "message": "success", "data": {...}}
启动：uvicorn backend.app.main:app --reload
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .core.config import get_settings
from .core.exceptions import AppError
from .core.logging import get_logger, setup_logging
from .middleware.request_log import RequestLogMiddleware
from .routers import health

setup_logging()
logger = get_logger("app")
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("service starting: env=%s log_level=%s", settings.APP_ENV, settings.LOG_LEVEL)
    yield
    logger.info("service stopped")


app = FastAPI(
    title="电商用户行为分析与智能推荐平台",
    description="数据生成 → ETL → 分析 → 预测 → 推荐 → API 的数据应用闭环",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(RequestLogMiddleware)
app.include_router(health.router, prefix="/api")


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    return JSONResponse(
        status_code=exc.http_status,
        content={"code": exc.code, "message": exc.message, "data": None},
    )


@app.exception_handler(StarletteHTTPException)
async def http_error_handler(request: Request, exc: StarletteHTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.status_code * 100, "message": str(exc.detail), "data": None},
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={"code": 42200, "message": "参数校验失败", "data": exc.errors()},
    )


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception):
    logger.error("unhandled error on %s %s: %s", request.method, request.url.path, exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"code": 50000, "message": "服务器内部错误", "data": None},
    )