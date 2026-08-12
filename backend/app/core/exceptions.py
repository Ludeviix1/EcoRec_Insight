"""业务异常体系：所有可控错误统一为 AppError，并在 main.py 转换为统一响应格式。

响应格式：{"code": <非0>, "message": "...", "data": null}
"""


class AppError(Exception):
    def __init__(self, message: str, code: int = 1, http_status: int = 400):
        super().__init__(message)
        self.message = message
        self.code = code
        self.http_status = http_status


class NotFoundError(AppError):
    """资源不存在（对应 HTTP 404）。"""

    def __init__(self, message: str = "资源不存在"):
        super().__init__(message, code=40400, http_status=404)  # type: ignore[misc]


class ValidationError(AppError):
    """业务参数校验失败。"""

    def __init__(self, message: str = "参数校验失败"):
        super().__init__(message, code=40000, http_status=400)  # type: ignore[misc]