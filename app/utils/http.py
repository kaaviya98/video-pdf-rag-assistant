from __future__ import annotations

import requests


def close_http_response(response: requests.Response | None) -> None:
    if response is not None:
        response.close()
