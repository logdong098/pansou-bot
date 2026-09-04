"""Pre-flight validation for cloud-drive share links."""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List
from urllib.parse import urlparse

import httpx

# Quark's share page is only an SPA shell: HTTP 200 does not mean the
# share exists. The authoritative result is the JSON returned by the
# share-detail API used by the official page.
_DETAIL_PATH = "/1/clouddrive/share/sharepage/v2/detail"
_INVALID_CODES = {41012, 41013, 41014, 41015}


def is_live_quark_url(url: str, timeout: float = 8.0) -> bool:
    """Return True only when Quark's share-detail API confirms the share.

    The browser page itself always returns 200. We therefore extract the
    `pwd_id` from `/s/<id>` and call the same detail endpoint as the
    official share SPA. Any non-200 response, invalid/removed code, or
    malformed success payload is treated as unavailable.
    """
    try:
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.netloc.lower() != "pan.quark.cn":
            return False
        match = re.fullmatch(r"/s/([A-Za-z0-9]+)", parsed.path.rstrip("/"))
        if not match:
            return False
        pwd_id = match.group(1)
        api_url = f"https://pan.quark.cn{_DETAIL_PATH}?pr=ucpro&fr=h5&format=png"
        payload = {
            "pwd_id": pwd_id,
            "passcode": "",
            "pdir_fid": "0",
            "force": 0,
            "page": 1,
            "size": 50,
            "fetch_banner": 1,
            "fetch_share": 1,
            "fetch_relate_conversation": 1,
            "fetch_total": 1,
            "fetch_sub_file_cnt": 1,
            "sort": "file_type:asc,file_name:asc",
            "support_visit_limit_private_share": True,
        }
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json;charset=UTF-8",
            "Referer": url,
            "User-Agent": "Mozilla/5.0",
        }
        response = httpx.post(
            api_url,
            json=payload,
            follow_redirects=False,
            timeout=timeout,
            headers=headers,
        )
        if response.status_code != 200:
            # Quark itself uses 404 for the cancelled-share response.
            return False
        data = response.json()
        if not isinstance(data, dict):
            return False
        code = data.get("code")
        if isinstance(code, int) and code in _INVALID_CODES:
            return False
        # A valid share response has detail_info / file information under
        # data. Do not accept a generic HTTP 200 or an error-shaped object.
        body = data.get("data")
        if not isinstance(body, dict):
            return False
        return bool(
            body.get("detail_info")
            or body.get("file_list")
            or body.get("share_info")
            or body.get("share_detail")
        )
    except (httpx.HTTPError, ValueError, TypeError, KeyError):
        return False


def filter_live_quark_resources(
    resources: List[Dict[str, Any]],
    *,
    max_workers: int = 6,
) -> List[Dict[str, Any]]:
    """Drop resources whose Quark share URL is unavailable.

    Non-Quark resources are left untouched so this helper remains safe if
    a future deployment enables multiple PAN_TYPES.
    """
    if not resources:
        return []
    workers = max(1, min(max_workers, len(resources)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        checks = list(pool.map(
            lambda item: (
                item,
                is_live_quark_url(item.get("url", ""))
                if item.get("pan_type", "").lower() == "quark"
                else True,
            ),
            resources,
        ))
    return [item for item, live in checks if live]
