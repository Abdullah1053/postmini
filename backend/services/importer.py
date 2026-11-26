import json

def normalize_request(r):
    headers = []
    raw_h = r.get("headers", [])
    if isinstance(raw_h, dict):
        headers = [{"key": k, "value": str(v), "enabled": True} for k, v in raw_h.items()]
    elif isinstance(raw_h, list):
        for item in raw_h:
            if isinstance(item, dict) and item.get("key"):
                headers.append({
                    "key": item["key"],
                    "value": str(item.get("value", "")),
                    "enabled": item.get("enabled", True)
                })

    params = []
    raw_p = r.get("params", [])
    if isinstance(raw_p, dict):
        params = [{"key": k, "value": str(v), "enabled": True} for k, v in raw_p.items()]
    elif isinstance(raw_p, list):
        for item in raw_p:
            if isinstance(item, dict) and item.get("key"):
                params.append({
                    "key": item["key"],
                    "value": str(item.get("value", "")),
                    "enabled": item.get("enabled", True)
                })

    body_form = []
    raw_bf = r.get("body_form", [])
    if isinstance(raw_bf, dict):
        body_form = [{"key": k, "value": str(v), "enabled": True} for k, v in raw_bf.items()]
    elif isinstance(raw_bf, list):
        for item in raw_bf:
            if isinstance(item, dict) and item.get("key"):
                body_form.append({
                    "key": item["key"],
                    "value": str(item.get("value", "")),
                    "enabled": item.get("enabled", True)
                })

    raw_body = r.get("body_raw", "")
    if isinstance(raw_body, (dict, list)):
        raw_body = json.dumps(raw_body, indent=2)

    return {
        "name": r.get("name") or "Untitled Request",
        "method": (r.get("method") or "GET").upper(),
        "url": r.get("url") or "",
        "headers": headers,
        "params": params,
        "body_type": r.get("body_type") or ("raw_json" if raw_body else "none"),
        "body_raw": str(raw_body or ""),
        "body_form": body_form
    }

def parse_collection_payload(raw_data):
    if isinstance(raw_data, list):
        return {
            "name": "Imported Requests",
            "base_url": "",
            "requests": [normalize_request(r) for r in raw_data if isinstance(r, dict)]
        }

    if not isinstance(raw_data, dict):
        raise ValueError("Expected a JSON object or list.")

    # 1. Postman Collection (v2.0 or v2.1)
    if "info" in raw_data and "item" in raw_data:
        project_name = raw_data.get("info", {}).get("name", "Imported Postman Collection")
        base_url = ""
        for v in raw_data.get("variable", []):
            if v.get("key") in ["baseUrl", "base_url", "BASE_URL", "host", "url"]:
                base_url = v.get("value", "")
                break

        flat_requests = []
        def extract_postman_items(items):
            for it in items:
                if "item" in it and isinstance(it["item"], list):
                    extract_postman_items(it["item"])
                elif "request" in it:
                    req_obj = it["request"]
                    name = it.get("name", "Request")
                    method = "GET"
                    url = ""
                    headers = []
                    params = []
                    body_type = "none"
                    body_raw = ""
                    body_form = []

                    if isinstance(req_obj, str):
                        url = req_obj
                    elif isinstance(req_obj, dict):
                        method = req_obj.get("method", "GET").upper()
                        raw_url = req_obj.get("url")
                        if isinstance(raw_url, str):
                            url = raw_url
                        elif isinstance(raw_url, dict):
                            url = raw_url.get("raw", "")
                            for q in raw_url.get("query", []):
                                if isinstance(q, dict) and q.get("key"):
                                    params.append({
                                        "key": q.get("key", ""),
                                        "value": q.get("value", ""),
                                        "enabled": not q.get("disabled", False)
                                    })

                        for h in req_obj.get("header", []):
                            if isinstance(h, dict) and h.get("key"):
                                headers.append({
                                    "key": h.get("key", ""),
                                    "value": h.get("value", ""),
                                    "enabled": not h.get("disabled", False)
                                })

                        b = req_obj.get("body", {})
                        mode = b.get("mode", "")
                        if mode == "raw":
                            body_type = "raw_json"
                            body_raw = b.get("raw", "")
                        elif mode in ["formdata", "urlencoded"]:
                            body_type = "form_data"
                            f_items = b.get("formdata" if mode == "formdata" else "urlencoded", [])
                            for f in f_items:
                                if isinstance(f, dict) and f.get("key"):
                                    body_form.append({
                                        "key": f.get("key", ""),
                                        "value": f.get("value", ""),
                                        "enabled": not f.get("disabled", False)
                                    })

                    flat_requests.append({
                        "name": name,
                        "method": method,
                        "url": url,
                        "headers": headers,
                        "params": params,
                        "body_type": body_type,
                        "body_raw": body_raw,
                        "body_form": body_form
                    })

        extract_postman_items(raw_data.get("item", []))
        return {
            "name": project_name,
            "base_url": base_url,
            "requests": flat_requests
        }

    # 2. Native PostMini format
    project_name = raw_data.get("name") or raw_data.get("project_name") or "Imported Collection"
    base_url = raw_data.get("base_url") or raw_data.get("baseUrl") or ""
    requests_list = raw_data.get("requests", [])

    return {
        "name": project_name,
        "base_url": base_url,
        "requests": [normalize_request(r) for r in requests_list if isinstance(r, dict)]
    }
