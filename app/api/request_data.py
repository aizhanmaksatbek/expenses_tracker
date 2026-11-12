import json
from typing import Any

from fastapi import HTTPException, Request, status


async def parse_request_data(request: Request) -> tuple[dict[str, Any], bool]:
    content_type = request.headers.get("content-type", "")
    if "application/x-www-form-urlencoded" in content_type:
        return dict(await request.form()), True
    try:
        body = await request.json()
    except (json.JSONDecodeError, ValueError):
        message = "Request body must be valid JSON or form data."
        raise HTTPException(status.HTTP_400_BAD_REQUEST, message) from None
    if not isinstance(body, dict):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Request body must be an object.")
    return body, False
