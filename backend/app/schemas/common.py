"""通用响应模型：全项目统一 {"code", "message", "data"} 结构。"""

from typing import Generic, Optional, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    code: int = 0
    message: str = "success"
    data: Optional[T] = None


def ok(data=None, message: str = "success") -> ApiResponse:
    return ApiResponse(code=0, message=message, data=data)