import json
import time
import requests
from requests.exceptions import Timeout, ConnectionError, RequestException

def resolve_url(raw_url, base_url):
    raw_url = (raw_url or "").strip()
    base_url = (base_url or "").strip().rstrip("/")
    if not raw_url:
        return base_url

    for var in ["{{baseUrl}}", "{{base_url}}", "{{BASE_URL}}", "{{BaseUrl}}"]:
        if var in raw_url:
            raw_url = raw_url.replace(var, base_url)

    if raw_url.startswith("/") and base_url:
        return base_url + raw_url

    if not (raw_url.startswith("http://") or raw_url.startswith("https://")) and base_url:
        return f"{base_url}/{raw_url.lstrip('/')}"

    return raw_url

def execute_http_request(data, base_url=""):
    method = (data.get("method") or "GET").upper()
    raw_url = data.get("url", "")
    final_url = resolve_url(raw_url, base_url)
    if not final_url:
        return {"error": "No URL provided", "status_code": 400}, 400

    if not (final_url.startswith("http://") or final_url.startswith("https://")):
        final_url = "http://" + final_url

    params_list = data.get("params", [])
    query_params = {}
    for item in params_list:
        if isinstance(item, dict) and item.get("enabled", True) and item.get("key"):
            query_params[item["key"]] = item.get("value", "")

    headers_list = data.get("headers", [])
    req_headers = {}
    for item in headers_list:
        if isinstance(item, dict) and item.get("enabled", True) and item.get("key"):
            req_headers[item["key"]] = item.get("value", "")

    body_type = data.get("body_type", "none")
    body_data = None
    body_json = None

    if body_type == "raw_json":
        raw_body_str = data.get("body_raw", "").strip()
        if raw_body_str:
            try:
                body_json = json.loads(raw_body_str)
            except Exception:
                body_data = raw_body_str.encode("utf-8")
            if not any(k.lower() == "content-type" for k in req_headers):
                req_headers["Content-Type"] = "application/json"
    elif body_type == "form_data":
        form_list = data.get("body_form", [])
        form_dict = {}
        for item in form_list:
            if isinstance(item, dict) and item.get("enabled", True) and item.get("key"):
                form_dict[item["key"]] = item.get("value", "")
        body_data = form_dict

    timeout_sec = float(data.get("timeout", 30))
    start_time = time.perf_counter()
    try:
        kwargs = {
            "method": method,
            "url": final_url,
            "params": query_params if query_params else None,
            "headers": req_headers if req_headers else None,
            "timeout": timeout_sec,
            "allow_redirects": True
        }
        if body_json is not None:
            kwargs["json"] = body_json
        elif body_data is not None:
            kwargs["data"] = body_data

        resp = requests.request(**kwargs)
        duration_ms = round((time.perf_counter() - start_time) * 1000)

        is_json = False
        parsed_body = None
        raw_text = resp.text

        try:
            parsed_body = resp.json()
            is_json = True
        except Exception:
            parsed_body = raw_text

        content_size_bytes = len(resp.content) if resp.content else 0
        resp_headers = [{"key": k, "value": v} for k, v in resp.headers.items()]

        return {
            "success": True,
            "status_code": resp.status_code,
            "status_text": resp.reason,
            "duration_ms": duration_ms,
            "size_bytes": content_size_bytes,
            "headers": resp_headers,
            "is_json": is_json,
            "body": parsed_body,
            "raw_text": raw_text,
            "effective_url": resp.url
        }, 200

    except Timeout:
        duration_ms = round((time.perf_counter() - start_time) * 1000)
        return {
            "success": False,
            "status_code": 408,
            "status_text": "Request Timeout",
            "duration_ms": duration_ms,
            "error": f"Request timed out after {timeout_sec} seconds.",
            "headers": [],
            "body": None,
            "effective_url": final_url
        }, 200
    except ConnectionError as ce:
        duration_ms = round((time.perf_counter() - start_time) * 1000)
        return {
            "success": False,
            "status_code": 0,
            "status_text": "Connection Error",
            "duration_ms": duration_ms,
            "error": f"Failed to establish connection to {final_url}. {str(ce)}",
            "headers": [],
            "body": None,
            "effective_url": final_url
        }, 200
    except RequestException as re:
        duration_ms = round((time.perf_counter() - start_time) * 1000)
        return {
            "success": False,
            "status_code": 0,
            "status_text": "Request Failed",
            "duration_ms": duration_ms,
            "error": str(re),
            "headers": [],
            "body": None,
            "effective_url": final_url
        }, 200
