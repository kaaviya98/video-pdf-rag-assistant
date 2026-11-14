import requests
from typing import Optional

from django.conf import settings

from app.utils.http import close_http_response


def ping_health_check(
    check_type: str,
    status: str,
    asset_id: str,
    error_message: Optional[str] = None,
    custom_data: Optional[dict] = None,
) -> None:
    health_check_urls = getattr(settings, "HEALTH_CHECK_URLS", {})
    health_check_url = health_check_urls.get(check_type)

    if not health_check_url:
        return

    try:
        message = (
            f"{check_type.replace('_', ' ').title()} {status} for asset {asset_id}"
        )
        if error_message:
            message += f" - Error: {error_message}"

        payload = {
            "message": message,
            "asset_id": asset_id,
            "status": status,
            "check_type": check_type,
        }

        if custom_data:
            payload.update(custom_data)

        response = requests.post(
            health_check_url,
            json=payload,
            timeout=10,
        )
        try:
            response.raise_for_status()
        finally:
            close_http_response(response)

    except Exception:
        pass
