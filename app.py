import os
import json
import time
from datetime import datetime
from flask import Flask, request, jsonify, render_template_string
from flask_sqlalchemy import SQLAlchemy
import requests
from requests.exceptions import Timeout, ConnectionError, RequestException

# Initialize Flask App
app = Flask(__name__)
db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "postmini.db")
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

# ==============================================================================
# Database Models
# ==============================================================================
class Project(db.Model):
    __tablename__ = "projects"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    base_url = db.Column(db.String(500), default="")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    requests = db.relationship(
        "ApiRequest",
        backref="project",
        cascade="all, delete-orphan",
        lazy=True,
        order_by="ApiRequest.id"
    )

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "base_url": self.base_url or "",
            "request_count": len(self.requests),
            "created_at": self.created_at.isoformat() if self.created_at else None
        }

class ApiRequest(db.Model):
    __tablename__ = "api_requests"
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    name = db.Column(db.String(120), nullable=False, default="New Request")
    method = db.Column(db.String(10), nullable=False, default="GET")
    url = db.Column(db.Text, default="")
    headers_json = db.Column(db.Text, default="[]")
    params_json = db.Column(db.Text, default="[]")
    body_type = db.Column(db.String(20), default="none")  # none, raw_json, form_data
    body_raw = db.Column(db.Text, default="")
    body_form_json = db.Column(db.Text, default="[]")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        try:
            headers = json.loads(self.headers_json) if self.headers_json else []
        except Exception:
            headers = []
        try:
            params = json.loads(self.params_json) if self.params_json else []
        except Exception:
            params = []
        try:
            body_form = json.loads(self.body_form_json) if self.body_form_json else []
        except Exception:
            body_form = []

        return {
            "id": self.id,
            "project_id": self.project_id,
            "name": self.name,
            "method": self.method,
            "url": self.url or "",
            "headers": headers,
            "params": params,
            "body_type": self.body_type or "none",
            "body_raw": self.body_raw or "",
            "body_form": body_form,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }

# ==============================================================================
# Collection Parsing & Normalization Helper
# ==============================================================================
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
    """
    Parses both PostMini format and standard Postman v2.0/v2.1 collections.
    """
    if isinstance(raw_data, list):
        return {
            "name": "Imported Requests",
            "base_url": "",
            "requests": [normalize_request(r) for r in raw_data if isinstance(r, dict)]
        }

    if not isinstance(raw_data, dict):
        raise ValueError("Expected a JSON object or list.")

    # 1. Check if standard Postman Collection (v2.0 or v2.1)
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

# ==============================================================================
# API Endpoints
# ==============================================================================
@app.route("/api/projects", methods=["GET"])
def get_projects():
    projects = Project.query.order_by(Project.created_at.desc()).all()
    return jsonify([p.to_dict() for p in projects])

@app.route("/api/projects", methods=["POST"])
def create_project():
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Project name is required"}), 400
    base_url = (data.get("base_url") or "").strip()
    project = Project(name=name, base_url=base_url)
    db.session.add(project)
    db.session.commit()
    return jsonify(project.to_dict()), 201

@app.route("/api/projects/<int:project_id>", methods=["PUT"])
def update_project(project_id):
    project = db.session.get(Project, project_id)
    if not project:
        return jsonify({"error": "Project not found"}), 404
    data = request.get_json() or {}
    if "name" in data and data["name"].strip():
        project.name = data["name"].strip()
    if "base_url" in data:
        project.base_url = data["base_url"].strip()
    db.session.commit()
    return jsonify(project.to_dict())

@app.route("/api/projects/<int:project_id>", methods=["DELETE"])
def delete_project(project_id):
    project = db.session.get(Project, project_id)
    if not project:
        return jsonify({"error": "Project not found"}), 404
    db.session.delete(project)
    db.session.commit()
    return jsonify({"success": True})

@app.route("/api/projects/<int:project_id>/requests", methods=["GET"])
def get_project_requests(project_id):
    project = db.session.get(Project, project_id)
    if not project:
        return jsonify({"error": "Project not found"}), 404
    reqs = ApiRequest.query.filter_by(project_id=project_id).order_by(ApiRequest.id.asc()).all()
    return jsonify([r.to_dict() for r in reqs])

@app.route("/api/projects/<int:project_id>/requests", methods=["POST"])
def create_request(project_id):
    project = db.session.get(Project, project_id)
    if not project:
        return jsonify({"error": "Project not found"}), 404
    data = request.get_json() or {}
    name = (data.get("name") or "New Request").strip()
    req = ApiRequest(
        project_id=project_id,
        name=name,
        method=data.get("method", "GET").upper(),
        url=data.get("url", ""),
        headers_json=json.dumps(data.get("headers", [])),
        params_json=json.dumps(data.get("params", [])),
        body_type=data.get("body_type", "none"),
        body_raw=data.get("body_raw", ""),
        body_form_json=json.dumps(data.get("body_form", []))
    )
    db.session.add(req)
    db.session.commit()
    return jsonify(req.to_dict()), 201

@app.route("/api/requests/<int:req_id>", methods=["GET"])
def get_request_detail(req_id):
    req_item = db.session.get(ApiRequest, req_id)
    if not req_item:
        return jsonify({"error": "Request not found"}), 404
    return jsonify(req_item.to_dict())

@app.route("/api/requests/<int:req_id>", methods=["PUT"])
def update_request_detail(req_id):
    req_item = db.session.get(ApiRequest, req_id)
    if not req_item:
        return jsonify({"error": "Request not found"}), 404
    data = request.get_json() or {}
    if "name" in data:
        req_item.name = data["name"].strip() or "Untitled Request"
    if "method" in data:
        req_item.method = data["method"].upper()
    if "url" in data:
        req_item.url = data["url"]
    if "headers" in data:
        req_item.headers_json = json.dumps(data["headers"])
    if "params" in data:
        req_item.params_json = json.dumps(data["params"])
    if "body_type" in data:
        req_item.body_type = data["body_type"]
    if "body_raw" in data:
        req_item.body_raw = data["body_raw"]
    if "body_form" in data:
        req_item.body_form_json = json.dumps(data["body_form"])
    db.session.commit()
    return jsonify(req_item.to_dict())

@app.route("/api/requests/<int:req_id>", methods=["DELETE"])
def delete_request_detail(req_id):
    req_item = db.session.get(ApiRequest, req_id)
    if not req_item:
        return jsonify({"error": "Request not found"}), 404
    db.session.delete(req_item)
    db.session.commit()
    return jsonify({"success": True})

@app.route("/api/import", methods=["POST"])
def import_collection():
    data = request.get_json()
    if not data:
        return jsonify({"error": "No JSON payload provided"}), 400
    try:
        parsed = parse_collection_payload(data)
    except Exception as e:
        return jsonify({"error": f"Failed to parse collection: {str(e)}"}), 400

    project = Project(
        name=parsed.get("name") or "Imported Project",
        base_url=parsed.get("base_url", "")
    )
    db.session.add(project)
    db.session.flush()

    req_objects = []
    for r in parsed.get("requests", []):
        req_obj = ApiRequest(
            project_id=project.id,
            name=r.get("name", "Request"),
            method=r.get("method", "GET"),
            url=r.get("url", ""),
            headers_json=json.dumps(r.get("headers", [])),
            params_json=json.dumps(r.get("params", [])),
            body_type=r.get("body_type", "none"),
            body_raw=r.get("body_raw", ""),
            body_form_json=json.dumps(r.get("body_form", []))
        )
        db.session.add(req_obj)
        req_objects.append(req_obj)

    db.session.commit()
    return jsonify({
        "success": True,
        "project": project.to_dict(),
        "imported_count": len(req_objects)
    }), 201

# ==============================================================================
# Request Execution Engine
# ==============================================================================
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

@app.route("/api/execute", methods=["POST"])
def execute_request():
    data = request.get_json() or {}
    method = (data.get("method") or "GET").upper()
    raw_url = data.get("url", "")
    base_url = data.get("base_url", "")
    project_id = data.get("project_id")

    if not base_url and project_id:
        proj = db.session.get(Project, project_id)
        if proj:
            base_url = proj.base_url

    final_url = resolve_url(raw_url, base_url)
    if not final_url:
        return jsonify({"error": "No URL provided"}), 400

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

        return jsonify({
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
        })

    except Timeout:
        duration_ms = round((time.perf_counter() - start_time) * 1000)
        return jsonify({
            "success": False,
            "status_code": 408,
            "status_text": "Request Timeout",
            "duration_ms": duration_ms,
            "error": f"Request timed out after {timeout_sec} seconds.",
            "headers": [],
            "body": None,
            "effective_url": final_url
        })
    except ConnectionError as ce:
        duration_ms = round((time.perf_counter() - start_time) * 1000)
        return jsonify({
            "success": False,
            "status_code": 0,
            "status_text": "Connection Error",
            "duration_ms": duration_ms,
            "error": f"Failed to establish connection to {final_url}. {str(ce)}",
            "headers": [],
            "body": None,
            "effective_url": final_url
        })
    except RequestException as re:
        duration_ms = round((time.perf_counter() - start_time) * 1000)
        return jsonify({
            "success": False,
            "status_code": 0,
            "status_text": "Request Failed",
            "duration_ms": duration_ms,
            "error": str(re),
            "headers": [],
            "body": None,
            "effective_url": final_url
        })

# ==============================================================================
# UI Template (Vanilla HTML/CSS/JS, zero CDN dependencies)
# ==============================================================================
HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>PostMini - Modern API Client</title>
  <style>
    :root {
      --bg-dark: #0f172a;
      --bg-sidebar: #131d34;
      --bg-panel: #1e293b;
      --bg-input: #0f172a;
      --border-color: #334155;
      --border-focus: #3b82f6;
      --text-main: #f8fafc;
      --text-muted: #94a3b8;
      --accent: #3b82f6;
      --accent-hover: #2563eb;
      --success: #10b981;
      --warning: #f59e0b;
      --danger: #ef4444;
      --font-mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
    }

    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background: var(--bg-dark);
      color: var(--text-main);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
      height: 100vh;
      display: flex;
      overflow: hidden;
    }

    /* Layout */
    .sidebar {
      width: 320px;
      min-width: 280px;
      background: var(--bg-sidebar);
      border-right: 1px solid var(--border-color);
      display: flex;
      flex-direction: column;
      height: 100%;
    }

    .main {
      flex: 1;
      display: flex;
      flex-direction: column;
      height: 100%;
      overflow: hidden;
    }

    /* Navigation Header */
    .top-nav {
      height: 48px;
      background: #0b1120;
      border-bottom: 1px solid var(--border-color);
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0 16px;
    }
    .nav-tabs {
      display: flex;
      gap: 6px;
    }
    .nav-tab-btn {
      background: transparent;
      border: 1px solid transparent;
      color: var(--text-muted);
      padding: 6px 14px;
      border-radius: 6px;
      font-size: 0.85rem;
      font-weight: 600;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 6px;
      transition: all 0.15s ease;
    }
    .nav-tab-btn:hover { color: #fff; background: rgba(255,255,255,0.05); }
    .nav-tab-btn.active {
      color: #93c5fd;
      background: rgba(59, 130, 246, 0.15);
      border-color: rgba(59, 130, 246, 0.3);
    }

    /* Sidebar Components */
    .sidebar-header {
      padding: 14px 16px;
      border-bottom: 1px solid var(--border-color);
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
    }
    .brand {
      font-weight: 700;
      font-size: 1.15rem;
      display: flex;
      align-items: center;
      gap: 8px;
      color: #60a5fa;
    }
    .btn {
      background: var(--accent);
      color: #fff;
      border: none;
      border-radius: 6px;
      padding: 6px 12px;
      font-size: 0.85rem;
      font-weight: 600;
      cursor: pointer;
      transition: background 0.15s ease, opacity 0.15s ease;
      display: inline-flex;
      align-items: center;
      gap: 6px;
    }
    .btn:hover { background: var(--accent-hover); }
    .btn-secondary { background: #334155; color: var(--text-main); }
    .btn-secondary:hover { background: #475569; }
    .btn-danger { background: rgba(239, 68, 68, 0.2); color: #fca5a5; border: 1px solid rgba(239, 68, 68, 0.4); }
    .btn-danger:hover { background: var(--danger); color: #fff; }
    .btn-sm { padding: 4px 8px; font-size: 0.78rem; }
    .btn-icon { padding: 5px; background: transparent; border: none; color: var(--text-muted); cursor: pointer; border-radius: 4px; }
    .btn-icon:hover { color: #fff; background: rgba(255,255,255,0.1); }

    .sidebar-body {
      flex: 1;
      overflow-y: auto;
      padding: 12px;
    }

    .project-card {
      background: var(--bg-panel);
      border: 1px solid var(--border-color);
      border-radius: 8px;
      margin-bottom: 12px;
      overflow: hidden;
      transition: border-color 0.15s ease;
    }
    .project-card.active { border-color: var(--accent); }
    .project-card-header {
      padding: 10px 12px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      cursor: pointer;
      background: rgba(255, 255, 255, 0.02);
      border-bottom: 1px solid transparent;
    }
    .project-card.active .project-card-header { border-bottom-color: var(--border-color); }
    .project-title {
      font-weight: 600;
      font-size: 0.95rem;
      display: flex;
      align-items: center;
      gap: 8px;
      color: #e2e8f0;
    }
    .project-actions { display: flex; align-items: center; gap: 4px; }

    .project-details {
      padding: 10px 12px;
      background: rgba(15, 23, 42, 0.6);
      display: none;
    }
    .project-card.active .project-details { display: block; }
    .base-url-bar {
      display: flex;
      align-items: center;
      gap: 6px;
      margin-bottom: 10px;
    }
    .base-url-bar input {
      flex: 1;
      background: var(--bg-input);
      border: 1px solid var(--border-color);
      color: var(--text-main);
      border-radius: 4px;
      padding: 4px 8px;
      font-size: 0.8rem;
      font-family: var(--font-mono);
    }

    .requests-list {
      list-style: none;
      display: flex;
      flex-direction: column;
      gap: 4px;
    }
    .request-item {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 6px 8px;
      border-radius: 6px;
      cursor: pointer;
      font-size: 0.85rem;
      transition: background 0.15s ease;
      color: var(--text-muted);
    }
    .request-item:hover {
      background: rgba(255,255,255,0.05);
      color: var(--text-main);
    }
    .request-item.active {
      background: rgba(59, 130, 246, 0.15);
      color: #93c5fd;
      font-weight: 500;
    }
    .req-badge {
      font-size: 0.68rem;
      font-weight: 700;
      padding: 2px 5px;
      border-radius: 4px;
      min-width: 44px;
      text-align: center;
      font-family: var(--font-mono);
    }
    .badge-get { background: rgba(16, 185, 129, 0.15); color: #34d399; }
    .badge-post { background: rgba(245, 158, 11, 0.15); color: #fbbf24; }
    .badge-put { background: rgba(59, 130, 246, 0.15); color: #60a5fa; }
    .badge-delete { background: rgba(239, 68, 68, 0.15); color: #f87171; }
    .badge-patch { background: rgba(168, 85, 247, 0.15); color: #c084fc; }

    /* Main Workspace Views */
    .view-pane {
      display: none;
      flex: 1;
      height: 100%;
      flex-direction: column;
      overflow: hidden;
    }
    .view-pane.active { display: flex; }

    .top-bar {
      padding: 14px 20px;
      border-bottom: 1px solid var(--border-color);
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      background: var(--bg-sidebar);
    }
    .req-name-input {
      background: transparent;
      border: 1px solid transparent;
      color: var(--text-main);
      font-size: 1.1rem;
      font-weight: 600;
      padding: 4px 8px;
      border-radius: 4px;
      outline: none;
      flex: 1;
    }
    .req-name-input:focus {
      background: var(--bg-input);
      border-color: var(--border-color);
    }

    .request-builder {
      padding: 16px 20px;
      display: flex;
      flex-direction: column;
      gap: 14px;
      border-bottom: 1px solid var(--border-color);
      background: var(--bg-panel);
    }
    .url-bar { display: flex; gap: 8px; }
    .select-method {
      background: var(--bg-input);
      color: #38bdf8;
      font-weight: 700;
      font-family: var(--font-mono);
      border: 1px solid var(--border-color);
      border-radius: 6px;
      padding: 0 14px;
      font-size: 0.9rem;
      outline: none;
      cursor: pointer;
    }
    .url-input-container {
      flex: 1;
      position: relative;
      display: flex;
      align-items: center;
    }
    .url-input {
      width: 100%;
      background: var(--bg-input);
      border: 1px solid var(--border-color);
      color: var(--text-main);
      border-radius: 6px;
      padding: 10px 14px;
      font-size: 0.95rem;
      font-family: var(--font-mono);
      outline: none;
    }
    .url-input:focus { border-color: var(--border-focus); }
    .btn-run {
      background: #2563eb;
      padding: 10px 24px;
      font-size: 0.95rem;
      font-weight: 700;
      border-radius: 6px;
    }
    .btn-run:hover { background: #1d4ed8; }

    .url-hint {
      font-size: 0.78rem;
      color: var(--text-muted);
      display: flex;
      align-items: center;
      gap: 6px;
    }
    .url-hint code {
      background: rgba(255,255,255,0.06);
      padding: 2px 5px;
      border-radius: 4px;
      color: #93c5fd;
      font-family: var(--font-mono);
    }

    /* Tabs */
    .tabs-container {
      display: flex;
      border-bottom: 1px solid var(--border-color);
      gap: 8px;
    }
    .tab-btn {
      background: transparent;
      border: none;
      color: var(--text-muted);
      font-size: 0.85rem;
      font-weight: 600;
      padding: 8px 14px;
      cursor: pointer;
      border-bottom: 2px solid transparent;
      transition: color 0.15s, border-color 0.15s;
    }
    .tab-btn:hover { color: var(--text-main); }
    .tab-btn.active {
      color: var(--accent);
      border-bottom-color: var(--accent);
    }

    .tab-pane { display: none; padding-top: 12px; }
    .tab-pane.active { display: block; }

    /* Key-Value Tables */
    .kv-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 0.85rem;
    }
    .kv-table th {
      text-align: left;
      padding: 6px 8px;
      color: var(--text-muted);
      font-weight: 500;
      border-bottom: 1px solid var(--border-color);
    }
    .kv-table td { padding: 4px 6px; }
    .kv-table input[type="text"] {
      width: 100%;
      background: var(--bg-input);
      border: 1px solid var(--border-color);
      color: var(--text-main);
      padding: 6px 10px;
      border-radius: 4px;
      font-size: 0.85rem;
      font-family: var(--font-mono);
      outline: none;
    }
    .kv-table input[type="text"]:focus { border-color: var(--border-focus); }
    .kv-table input[type="checkbox"] {
      cursor: pointer;
      accent-color: var(--accent);
      transform: scale(1.1);
    }

    /* Body Types */
    .body-type-selector {
      display: flex;
      gap: 16px;
      margin-bottom: 10px;
      font-size: 0.85rem;
    }
    .body-type-selector label {
      display: flex;
      align-items: center;
      gap: 6px;
      cursor: pointer;
      color: var(--text-muted);
    }
    .body-type-selector input[type="radio"]:checked + span {
      color: #60a5fa;
      font-weight: 600;
    }

    .code-editor {
      width: 100%;
      height: 140px;
      background: var(--bg-input);
      border: 1px solid var(--border-color);
      color: #38bdf8;
      border-radius: 6px;
      padding: 10px;
      font-family: var(--font-mono);
      font-size: 0.85rem;
      resize: vertical;
      outline: none;
      line-height: 1.4;
    }
    .code-editor:focus { border-color: var(--border-focus); }

    /* Response View */
    .response-section {
      flex: 1;
      display: flex;
      flex-direction: column;
      overflow: hidden;
      background: var(--bg-dark);
    }
    .response-header {
      padding: 10px 20px;
      border-bottom: 1px solid var(--border-color);
      display: flex;
      align-items: center;
      justify-content: space-between;
      background: var(--bg-sidebar);
    }
    .response-metrics {
      display: flex;
      align-items: center;
      gap: 14px;
      font-size: 0.85rem;
      font-family: var(--font-mono);
    }
    .status-badge {
      padding: 3px 10px;
      border-radius: 12px;
      font-weight: 700;
      font-size: 0.8rem;
    }
    .status-2xx { background: rgba(16, 185, 129, 0.2); color: #34d399; border: 1px solid #059669; }
    .status-3xx { background: rgba(59, 130, 246, 0.2); color: #60a5fa; border: 1px solid #2563eb; }
    .status-4xx { background: rgba(245, 158, 11, 0.2); color: #fbbf24; border: 1px solid #d97706; }
    .status-5xx, .status-0 { background: rgba(239, 68, 68, 0.2); color: #f87171; border: 1px solid #dc2626; }

    .response-body-container {
      flex: 1;
      overflow: auto;
      padding: 16px 20px;
      position: relative;
    }
    .response-pre {
      font-family: var(--font-mono);
      font-size: 0.85rem;
      line-height: 1.5;
      color: #e2e8f0;
      white-space: pre-wrap;
      word-break: break-all;
    }

    /* Syntax Highlighting */
    .json-key { color: #93c5fd; }
    .json-string { color: #86efac; }
    .json-number { color: #fde047; }
    .json-boolean { color: #f472b6; }
    .json-null { color: #cbd5e1; font-style: italic; }

    /* Docs View Styles */
    .docs-container {
      flex: 1;
      overflow-y: auto;
      padding: 28px 40px;
      max-width: 960px;
      margin: 0 auto;
      width: 100%;
    }
    .docs-header {
      margin-bottom: 24px;
      border-bottom: 1px solid var(--border-color);
      padding-bottom: 16px;
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
    }
    .docs-card {
      background: var(--bg-panel);
      border: 1px solid var(--border-color);
      border-radius: 8px;
      padding: 20px;
      margin-bottom: 24px;
    }
    .docs-card h3 {
      font-size: 1.05rem;
      color: #93c5fd;
      margin-bottom: 10px;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }
    .prompt-box {
      background: var(--bg-input);
      border: 1px solid var(--border-color);
      border-radius: 6px;
      padding: 14px;
      font-family: var(--font-mono);
      font-size: 0.85rem;
      line-height: 1.5;
      color: #f1f5f9;
      white-space: pre-wrap;
      position: relative;
    }

    /* Modals */
    .modal-backdrop {
      position: fixed;
      top: 0; left: 0; right: 0; bottom: 0;
      background: rgba(0, 0, 0, 0.7);
      display: none;
      align-items: center;
      justify-content: center;
      z-index: 1000;
    }
    .modal-backdrop.show { display: flex; }
    .modal {
      background: var(--bg-panel);
      border: 1px solid var(--border-color);
      border-radius: 8px;
      width: 520px;
      max-width: 90vw;
      padding: 20px;
      box-shadow: 0 10px 30px rgba(0,0,0,0.6);
    }
    .modal h3 { margin-bottom: 14px; font-size: 1.1rem; }
    .modal-group { margin-bottom: 12px; }
    .modal-group label { display: block; font-size: 0.8rem; color: var(--text-muted); margin-bottom: 4px; }
    .modal-group input[type="text"], .modal-group textarea {
      width: 100%;
      background: var(--bg-input);
      border: 1px solid var(--border-color);
      color: var(--text-main);
      padding: 8px 10px;
      border-radius: 6px;
      font-size: 0.9rem;
      outline: none;
    }
    .modal-actions {
      display: flex;
      justify-content: flex-end;
      gap: 8px;
      margin-top: 16px;
    }

    .empty-state {
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      height: 100%;
      color: var(--text-muted);
      text-align: center;
      gap: 12px;
      padding: 20px;
    }
    .empty-state svg { width: 48px; height: 48px; stroke: #475569; }

    .spinner {
      border: 3px solid rgba(255, 255, 255, 0.1);
      border-left-color: var(--accent);
      border-radius: 50%;
      width: 20px;
      height: 20px;
      animation: spin 0.8s linear infinite;
      display: inline-block;
    }
    @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }

    .toast {
      position: fixed;
      bottom: 24px;
      right: 24px;
      background: #1e293b;
      border: 1px solid var(--border-color);
      color: #fff;
      padding: 10px 18px;
      border-radius: 6px;
      box-shadow: 0 6px 16px rgba(0,0,0,0.4);
      z-index: 2000;
      opacity: 0;
      transform: translateY(10px);
      transition: opacity 0.2s, transform 0.2s;
      pointer-events: none;
    }
    .toast.show { opacity: 1; transform: translateY(0); }
  </style>
</head>
<body>

  <!-- Left Sidebar: Projects & Requests -->
  <aside class="sidebar">
    <div class="sidebar-header">
      <div class="brand">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"></polygon></svg>
        <span>PostMini</span>
      </div>
      <div style="display: flex; gap: 6px;">
        <button class="btn btn-sm btn-secondary" onclick="openImportModal()" title="Import Collection JSON">📥 Import</button>
        <button class="btn btn-sm" onclick="openNewProjectModal()" title="New Project">+ Project</button>
      </div>
    </div>

    <div class="sidebar-body" id="projectsList">
      <!-- Populated via JS -->
    </div>
  </aside>

  <!-- Main View Area -->
  <main class="main" id="mainContainer">
    <!-- Top Navigation Header -->
    <header class="top-nav">
      <div class="nav-tabs">
        <button class="nav-tab-btn active" id="navBtnClient" onclick="switchMainView('client')">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="3" width="20" height="14" rx="2" ry="2"></rect><line x1="8" y1="21" x2="16" y2="21"></line><line x1="12" y1="17" x2="12" y2="21"></line></svg>
          API Workspace
        </button>
        <button class="nav-tab-btn" id="navBtnDocs" onclick="switchMainView('docs')">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"></path><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"></path></svg>
          Docs & AI Prompts
        </button>
      </div>
      <button class="btn btn-sm btn-secondary" onclick="openImportModal()">📥 Import Collection</button>
    </header>

    <!-- VIEW 1: API Workspace (Request Builder & Response) -->
    <div id="viewClient" class="view-pane active">
      <div id="noSelectionState" class="empty-state">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg>
        <h3>No Request Selected</h3>
        <p>Select a project and request from the sidebar, or create/import one to start testing.</p>
        <div style="margin-top: 10px; display: flex; gap: 8px;">
          <button class="btn btn-sm" onclick="openNewProjectModal()">+ Create Project</button>
          <button class="btn btn-sm btn-secondary" onclick="openImportModal()">📥 Import Collection</button>
        </div>
      </div>

      <div id="activeRequestContainer" style="display: none; height: 100%; flex-direction: column;">
        <!-- Top Action Bar -->
        <div class="top-bar">
          <input type="text" id="requestName" class="req-name-input" value="Untitled Request" placeholder="Request Name" onchange="autoSaveCurrentRequest()">
          <div style="display: flex; gap: 8px;">
            <button class="btn btn-secondary btn-sm" onclick="saveCurrentRequest()">Save</button>
            <button class="btn btn-danger btn-sm" onclick="deleteCurrentRequest()">Delete</button>
          </div>
        </div>

        <!-- Request Builder: Method, URL, Send -->
        <div class="request-builder">
          <div class="url-bar">
            <select id="requestMethod" class="select-method" onchange="autoSaveCurrentRequest()">
              <option value="GET">GET</option>
              <option value="POST">POST</option>
              <option value="PUT">PUT</option>
              <option value="DELETE">DELETE</option>
              <option value="PATCH">PATCH</option>
              <option value="HEAD">HEAD</option>
              <option value="OPTIONS">OPTIONS</option>
            </select>
            <div class="url-input-container">
              <input type="text" id="requestUrl" class="url-input" placeholder="https://api.example.com/users or {{baseUrl}}/users" onkeydown="handleUrlKeydown(event)" onchange="autoSaveCurrentRequest()">
            </div>
            <button class="btn btn-run" id="btnRun" onclick="runRequest()">
              <span>Run</span>
            </button>
          </div>

          <div class="url-hint">
            <span>Tip: Use <code>{{baseUrl}}</code> or start URL with <code>/</code> to use project base URL. Shortcut: <code>Ctrl + Enter</code> to run.</span>
          </div>

          <!-- Request Tabs (Params, Headers, Body) -->
          <div class="tabs-container">
            <button class="tab-btn active" onclick="switchReqTab('params')">Params <span id="paramsCount"></span></button>
            <button class="tab-btn" onclick="switchReqTab('headers')">Headers <span id="headersCount"></span></button>
            <button class="tab-btn" onclick="switchReqTab('body')">Body</button>
          </div>

          <!-- Tab 1: Query Params -->
          <div id="tab-params" class="tab-pane active">
            <table class="kv-table" id="paramsTable">
              <thead>
                <tr>
                  <th style="width: 32px;"></th>
                  <th style="width: 45%;">Key</th>
                  <th style="width: 45%;">Value</th>
                  <th style="width: 32px;"></th>
                </tr>
              </thead>
              <tbody id="paramsTableBody"></tbody>
            </table>
            <button class="btn btn-secondary btn-sm" style="margin-top: 8px;" onclick="addKvRow('paramsTableBody')">+ Add Parameter</button>
          </div>

          <!-- Tab 2: Headers -->
          <div id="tab-headers" class="tab-pane">
            <table class="kv-table" id="headersTable">
              <thead>
                <tr>
                  <th style="width: 32px;"></th>
                  <th style="width: 45%;">Header Key</th>
                  <th style="width: 45%;">Header Value</th>
                  <th style="width: 32px;"></th>
                </tr>
              </thead>
              <tbody id="headersTableBody"></tbody>
            </table>
            <button class="btn btn-secondary btn-sm" style="margin-top: 8px;" onclick="addKvRow('headersTableBody')">+ Add Header</button>
          </div>

          <!-- Tab 3: Request Body -->
          <div id="tab-body" class="tab-pane">
            <div class="body-type-selector">
              <label><input type="radio" name="bodyType" value="none" checked onchange="toggleBodyType('none')"> <span>None</span></label>
              <label><input type="radio" name="bodyType" value="raw_json" onchange="toggleBodyType('raw_json')"> <span>Raw JSON</span></label>
              <label><input type="radio" name="bodyType" value="form_data" onchange="toggleBodyType('form_data')"> <span>Form Data</span></label>
            </div>

            <div id="bodyTypeNone" style="color: var(--text-muted); font-size: 0.85rem; padding: 12px 0;">
              This request has no body payload.
            </div>

            <div id="bodyTypeJson" style="display: none;">
              <div style="display: flex; justify-content: flex-end; margin-bottom: 6px;">
                <button class="btn btn-secondary btn-sm" onclick="beautifyJsonBody()">Beautify JSON</button>
              </div>
              <textarea id="bodyRawJson" class="code-editor" placeholder='{\\n  "key": "value"\\n}' onchange="autoSaveCurrentRequest()"></textarea>
            </div>

            <div id="bodyTypeFormData" style="display: none;">
              <table class="kv-table" id="formDataTable">
                <thead>
                  <tr>
                    <th style="width: 32px;"></th>
                    <th style="width: 45%;">Key</th>
                    <th style="width: 45%;">Value</th>
                    <th style="width: 32px;"></th>
                  </tr>
                </thead>
                <tbody id="formDataTableBody"></tbody>
              </table>
              <button class="btn btn-secondary btn-sm" style="margin-top: 8px;" onclick="addKvRow('formDataTableBody')">+ Add Field</button>
            </div>
          </div>
        </div>

        <!-- Response Panel -->
        <div class="response-section">
          <div class="response-header">
            <div class="tabs-container" style="border: none;">
              <button class="tab-btn active" onclick="switchRespTab('body')">Response Body</button>
              <button class="tab-btn" onclick="switchRespTab('headers')">Response Headers <span id="respHeadersCount"></span></button>
            </div>
            <div class="response-metrics" id="responseMetrics">
              <span style="color: var(--text-muted);">No response yet</span>
            </div>
          </div>

          <div class="response-body-container">
            <div id="resp-tab-body">
              <div style="display: flex; justify-content: flex-end; margin-bottom: 8px;" id="copyRespBtnContainer">
                <button class="btn btn-secondary btn-sm" onclick="copyResponseBody()">Copy Response</button>
              </div>
              <pre class="response-pre" id="responseBodyDisplay"><span style="color: var(--text-muted);">Execute this request to see the response.</span></pre>
            </div>

            <div id="resp-tab-headers" style="display: none;">
              <table class="kv-table">
                <thead>
                  <tr>
                    <th style="width: 40%;">Header</th>
                    <th style="width: 60%;">Value</th>
                  </tr>
                </thead>
                <tbody id="respHeadersTableBody"></tbody>
              </table>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- VIEW 2: Documentation & AI Conversion Prompts -->
    <div id="viewDocs" class="view-pane">
      <div class="docs-container">
        <div class="docs-header">
          <div>
            <h1 style="font-size: 1.5rem; margin-bottom: 6px;">📖 PostMini Documentation & Prompt Helper</h1>
            <p style="color: var(--text-muted); font-size: 0.9rem;">Learn the clean, portable JSON collection format or use the AI prompt below to convert any Postman, cURL, or OpenAPI collection instantly.</p>
          </div>
          <button class="btn" onclick="openImportModal()">📥 Open Import Dialog</button>
        </div>

        <!-- Section 1: AI Prompt -->
        <div class="docs-card">
          <h3>
            <span>🤖 Reusable AI Conversion Prompt</span>
            <button class="btn btn-secondary btn-sm" onclick="copyPromptText()">📋 Copy Prompt</button>
          </h3>
          <p style="color: var(--text-muted); font-size: 0.85rem; margin-bottom: 12px;">
            Copy this prompt into ChatGPT, Claude, Gemini, or any LLM alongside your Postman export, OpenAPI specification, or cURL list to convert it cleanly into PostMini JSON:
          </p>
          <div class="prompt-box" id="aiPromptText">You are an API conversion assistant. Convert the provided API endpoints/collection (Postman, OpenAPI, cURL, or documentation) into the clean PostMini collection format.

Output ONLY a valid JSON object matching this exact schema:
{
  "name": "<Project Name>",
  "base_url": "<Base URL without trailing slash, e.g. https://api.example.com>",
  "requests": [
    {
      "name": "<Descriptive Name of Request>",
      "method": "GET | POST | PUT | DELETE | PATCH",
      "url": "<URL using {{baseUrl}}/path or full URL>",
      "headers": [
        {"key": "Header-Name", "value": "Header-Value", "enabled": true}
      ],
      "params": [
        {"key": "query_param_key", "value": "query_param_val", "enabled": true}
      ],
      "body_type": "none | raw_json | form_data",
      "body_raw": "<Stringified JSON payload if body_type is raw_json, else empty>",
      "body_form": [
        {"key": "field_name", "value": "field_val", "enabled": true}
      ]
    }
  ]
}

Conversion Rules:
1. Extract repeating hostnames into "base_url" and reference them in URLs as "{{baseUrl}}/path".
2. If the request has a JSON body, set "body_type": "raw_json" and place formatted JSON in "body_raw". Ensure a "Content-Type": "application/json" header is included.
3. If the request has form fields, set "body_type": "form_data" and place fields in "body_form".
4. Do not include markdown formatting or commentary outside of the JSON block.

Here is the API collection/endpoints to convert:
[PASTE YOUR POSTMAN COLLECTION / CURL / SPEC HERE]</div>
        </div>

        <!-- Section 2: Interactive Sample Collection -->
        <div class="docs-card">
          <h3>
            <span>📦 Sample Collection: E-Commerce & Auth API</span>
            <div style="display: flex; gap: 8px;">
              <button class="btn btn-secondary btn-sm" onclick="copySampleJson()">Copy JSON</button>
              <button class="btn btn-sm" onclick="importSampleDirectly()">✨ Import This Sample</button>
            </div>
          </h3>
          <p style="color: var(--text-muted); font-size: 0.85rem; margin-bottom: 12px;">
            Click <b>Import This Sample</b> to load this fully configured multi-endpoint project right into your PostMini workspace:
          </p>
          <div class="prompt-box" id="sampleJsonText" style="max-height: 280px; overflow-y: auto;">{
  "name": "DummyJSON Store API",
  "base_url": "https://dummyjson.com",
  "requests": [
    {
      "name": "Get All Products",
      "method": "GET",
      "url": "{{baseUrl}}/products",
      "headers": [
        {"key": "Accept", "value": "application/json", "enabled": true}
      ],
      "params": [
        {"key": "limit", "value": "10", "enabled": true},
        {"key": "skip", "value": "0", "enabled": true}
      ],
      "body_type": "none",
      "body_raw": ""
    },
    {
      "name": "Search Products",
      "method": "GET",
      "url": "{{baseUrl}}/products/search",
      "headers": [],
      "params": [
        {"key": "q", "value": "phone", "enabled": true}
      ],
      "body_type": "none",
      "body_raw": ""
    },
    {
      "name": "Add New Product",
      "method": "POST",
      "url": "{{baseUrl}}/products/add",
      "headers": [
        {"key": "Content-Type", "value": "application/json", "enabled": true}
      ],
      "params": [],
      "body_type": "raw_json",
      "body_raw": "{\\n  \\"title\\": \\"Wireless Headphones\\",\\n  \\"price\\": 89.99,\\n  \\"category\\": \\"electronics\\"\\n}"
    },
    {
      "name": "Delete Product",
      "method": "DELETE",
      "url": "{{baseUrl}}/products/1",
      "headers": [],
      "params": [],
      "body_type": "none",
      "body_raw": ""
    }
  ]
}</div>
        </div>

        <!-- Section 3: Direct Postman Compatibility -->
        <div class="docs-card">
          <h3><span>⚡ Direct Postman v2.0 / v2.1 Import</span></h3>
          <p style="color: var(--text-muted); font-size: 0.85rem; line-height: 1.6;">
            PostMini also has a built-in Postman parser! You don't even have to convert standard Postman files:
          </p>
          <ul style="color: var(--text-muted); font-size: 0.85rem; padding-left: 20px; line-height: 1.8; margin-top: 8px;">
            <li>In Postman, click on your collection &gt; <b>Export</b> &gt; <b>Collection v2.1 (recommended)</b>.</li>
            <li>Click <b>📥 Import</b> in PostMini, choose the <code>.json</code> file (or paste its content), and click <b>Import Collection</b>.</li>
            <li>PostMini automatically flattens folders, preserves URLs, query params, headers, and bodies!</li>
          </ul>
        </div>
      </div>
    </div>
  </main>

  <!-- Modal: Create / Edit Project -->
  <div class="modal-backdrop" id="projectModal">
    <div class="modal">
      <h3 id="modalProjectTitle">Create New Project</h3>
      <div class="modal-group">
        <label for="projectNameInput">Project Name</label>
        <input type="text" id="projectNameInput" placeholder="e.g. Auth Service">
      </div>
      <div class="modal-group">
        <label for="projectBaseUrlInput">Base URL (optional)</label>
        <input type="text" id="projectBaseUrlInput" placeholder="e.g. https://api.example.com">
      </div>
      <div class="modal-actions">
        <button class="btn btn-secondary" onclick="closeProjectModal()">Cancel</button>
        <button class="btn" onclick="submitProjectModal()">Save Project</button>
      </div>
    </div>
  </div>

  <!-- Modal: Import Collection -->
  <div class="modal-backdrop" id="importModal">
    <div class="modal">
      <h3>📥 Import Collection</h3>
      <p style="color: var(--text-muted); font-size: 0.82rem; margin-bottom: 12px;">
        Upload a JSON file or paste a collection in <b>PostMini format</b> or standard <b>Postman v2.0/v2.1 export</b>.
      </p>

      <div class="modal-group">
        <label for="importFileInput">Select .JSON file</label>
        <input type="file" id="importFileInput" accept=".json" onchange="handleImportFileSelect(event)" style="font-size: 0.85rem; color: var(--text-muted);">
      </div>

      <div class="modal-group">
        <label for="importJsonInput">Or Paste Collection JSON</label>
        <textarea id="importJsonInput" class="code-editor" style="height: 160px;" placeholder='{\n  "name": "My API",\n  "base_url": "https://api...",\n  "requests": [...]\n}'></textarea>
      </div>

      <div class="modal-actions">
        <button class="btn btn-secondary" onclick="closeImportModal()">Cancel</button>
        <button class="btn" id="btnSubmitImport" onclick="submitImport()">Import Collection</button>
      </div>
    </div>
  </div>

  <div class="toast" id="toast">Saved!</div>

  <script>
    // State
    let projects = [];
    let activeProjectId = null;
    let activeRequestId = null;
    let currentRequestData = null;
    let currentRawResponse = "";

    // DOM Elements
    const projectsListEl = document.getElementById("projectsList");
    const noSelectionStateEl = document.getElementById("noSelectionState");
    const activeRequestContainerEl = document.getElementById("activeRequestContainer");

    // Initialize
    document.addEventListener("DOMContentLoaded", () => {
      loadProjects();

      // Keyboard shortcuts
      document.addEventListener("keydown", (e) => {
        if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
          e.preventDefault();
          runRequest();
        } else if ((e.ctrlKey || e.metaKey) && e.key === "s") {
          e.preventDefault();
          saveCurrentRequest();
        }
      });
    });

    function showToast(msg) {
      const t = document.getElementById("toast");
      t.textContent = msg;
      t.classList.add("show");
      setTimeout(() => t.classList.remove("show"), 2200);
    }

    // View Switching (Workspace vs Docs)
    function switchMainView(viewName) {
      document.querySelectorAll(".nav-tab-btn").forEach(b => b.classList.remove("active"));
      document.querySelectorAll(".view-pane").forEach(p => p.classList.remove("active"));

      if (viewName === "client") {
        document.getElementById("navBtnClient").classList.add("active");
        document.getElementById("viewClient").classList.add("active");
      } else if (viewName === "docs") {
        document.getElementById("navBtnDocs").classList.add("active");
        document.getElementById("viewDocs").classList.add("active");
      }
    }

    // Projects CRUD
    async function loadProjects() {
      try {
        const res = await fetch("/api/projects");
        projects = await res.json();
        renderProjects();
        if (activeProjectId) {
          const exists = projects.some(p => p.id === activeProjectId);
          if (!exists && projects.length > 0) {
            selectProject(projects[0].id);
          }
        }
      } catch (err) {
        console.error("Failed to load projects", err);
      }
    }

    function renderProjects() {
      projectsListEl.innerHTML = "";
      if (projects.length === 0) {
        projectsListEl.innerHTML = `<div style="color: var(--text-muted); font-size: 0.85rem; text-align: center; padding: 20px 0;">No projects yet.<br><br><button class="btn btn-sm" onclick="openNewProjectModal()">+ New Project</button><br><br>or <a href="#" style="color: #60a5fa;" onclick="switchMainView('docs')">Import Sample</a></div>`;
        return;
      }

      projects.forEach(p => {
        const isActive = p.id === activeProjectId;
        const card = document.createElement("div");
        card.className = `project-card ${isActive ? 'active' : ''}`;
        card.id = `project-card-${p.id}`;

        card.innerHTML = `
          <div class="project-card-header" onclick="selectProject(${p.id})">
            <span class="project-title">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path></svg>
              ${escapeHtml(p.name)}
            </span>
            <div class="project-actions" onclick="event.stopPropagation()">
              <button class="btn-icon" title="New Request" onclick="createNewRequest(${p.id})">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="12" y1="5" x2="12" y2="19"></line><line x1="5" y1="12" x2="19" y2="12"></line></svg>
              </button>
              <button class="btn-icon" title="Delete Project" onclick="deleteProject(${p.id}, '${escapeHtml(p.name)}')">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg>
              </button>
            </div>
          </div>
          <div class="project-details">
            <div class="base-url-bar">
              <span style="font-size: 0.75rem; color: var(--text-muted);">Base URL:</span>
              <input type="text" value="${escapeHtml(p.base_url || '')}" placeholder="https://api..." onchange="updateProjectBaseUrl(${p.id}, this.value)">
            </div>
            <ul class="requests-list" id="req-list-${p.id}">
              <li style="color: var(--text-muted); font-size: 0.78rem;">Loading requests...</li>
            </ul>
          </div>
        `;

        projectsListEl.appendChild(card);
        if (isActive) {
          loadProjectRequests(p.id);
        }
      });
    }

    async function selectProject(projectId) {
      if (activeProjectId === projectId) return;
      activeProjectId = projectId;
      renderProjects();
    }

    async function loadProjectRequests(projectId) {
      try {
        const res = await fetch(`/api/projects/${projectId}/requests`);
        const reqs = await res.json();
        const listEl = document.getElementById(`req-list-${projectId}`);
        if (!listEl) return;

        listEl.innerHTML = "";
        if (reqs.length === 0) {
          listEl.innerHTML = `<li style="color: var(--text-muted); font-size: 0.78rem; padding: 4px;">No requests. Click <b>+</b> above.</li>`;
          return;
        }

        reqs.forEach(r => {
          const li = document.createElement("li");
          li.className = `request-item ${r.id === activeRequestId ? 'active' : ''}`;
          li.onclick = () => selectRequest(r.id);
          li.innerHTML = `
            <div style="display: flex; align-items: center; gap: 8px; overflow: hidden;">
              <span class="req-badge badge-${r.method.toLowerCase()}">${r.method}</span>
              <span style="white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">${escapeHtml(r.name)}</span>
            </div>
          `;
          listEl.appendChild(li);
        });

        if (activeRequestId && !reqs.some(r => r.id === activeRequestId)) {
          activeRequestId = null;
          showNoSelection();
        } else if (!activeRequestId && reqs.length > 0) {
          selectRequest(reqs[0].id);
        }
      } catch (err) {
        console.error("Failed to load requests", err);
      }
    }

    async function updateProjectBaseUrl(projectId, newUrl) {
      try {
        await fetch(`/api/projects/${projectId}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ base_url: newUrl })
        });
        const proj = projects.find(p => p.id === projectId);
        if (proj) proj.base_url = newUrl;
        showToast("Base URL saved");
      } catch (err) {
        console.error("Failed to update base url", err);
      }
    }

    async function deleteProject(projectId, name) {
      if (!confirm(`Delete project "${name}" and all its requests?`)) return;
      try {
        await fetch(`/api/projects/${projectId}`, { method: "DELETE" });
        if (activeProjectId === projectId) {
          activeProjectId = null;
          activeRequestId = null;
          showNoSelection();
        }
        loadProjects();
        showToast("Project deleted");
      } catch (err) {
        console.error("Failed to delete project", err);
      }
    }

    // Requests CRUD
    async function createNewRequest(projectId) {
      try {
        const res = await fetch(`/api/projects/${projectId}/requests`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name: "New Request", method: "GET", url: "" })
        });
        const newReq = await res.json();
        activeProjectId = projectId;
        activeRequestId = newReq.id;
        await loadProjects();
        selectRequest(newReq.id);
        switchMainView('client');
        showToast("Request created");
      } catch (err) {
        console.error("Failed to create request", err);
      }
    }

    async function selectRequest(reqId) {
      activeRequestId = reqId;
      try {
        const res = await fetch(`/api/requests/${reqId}`);
        currentRequestData = await res.json();
        populateRequestForm(currentRequestData);
        noSelectionStateEl.style.display = "none";
        activeRequestContainerEl.style.display = "flex";

        document.querySelectorAll(".request-item").forEach(el => el.classList.remove("active"));
        if (activeProjectId) {
          loadProjectRequests(activeProjectId);
        }
        switchMainView('client');
      } catch (err) {
        console.error("Failed to get request details", err);
      }
    }

    function showNoSelection() {
      noSelectionStateEl.style.display = "flex";
      activeRequestContainerEl.style.display = "none";
    }

    function populateRequestForm(data) {
      document.getElementById("requestName").value = data.name || "Untitled Request";
      document.getElementById("requestMethod").value = data.method || "GET";
      document.getElementById("requestUrl").value = data.url || "";

      populateKvTable("headersTableBody", data.headers || []);
      populateKvTable("paramsTableBody", data.params || []);
      const bodyType = data.body_type || "none";
      const radio = document.querySelector(`input[name="bodyType"][value="${bodyType}"]`);
      if (radio) radio.checked = true;
      toggleBodyType(bodyType);

      document.getElementById("bodyRawJson").value = data.body_raw || "";
      populateKvTable("formDataTableBody", data.body_form || []);

      document.getElementById("responseMetrics").innerHTML = `<span style="color: var(--text-muted);">Ready to send</span>`;
      document.getElementById("responseBodyDisplay").innerHTML = `<span style="color: var(--text-muted);">Press Run or Ctrl+Enter to execute</span>`;
      document.getElementById("respHeadersTableBody").innerHTML = "";
    }

    function getFormDataFromUi() {
      const headers = readKvTable("headersTableBody");
      const params = readKvTable("paramsTableBody");
      const bodyForm = readKvTable("formDataTableBody");
      const bodyType = document.querySelector('input[name="bodyType"]:checked').value;
      const bodyRaw = document.getElementById("bodyRawJson").value;

      return {
        name: document.getElementById("requestName").value.trim(),
        method: document.getElementById("requestMethod").value,
        url: document.getElementById("requestUrl").value.trim(),
        headers: headers,
        params: params,
        body_type: bodyType,
        body_raw: bodyRaw,
        body_form: bodyForm
      };
    }

    async function saveCurrentRequest() {
      if (!activeRequestId) return;
      const payload = getFormDataFromUi();
      try {
        const res = await fetch(`/api/requests/${activeRequestId}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });
        currentRequestData = await res.json();
        showToast("Request saved!");
        if (activeProjectId) {
          loadProjectRequests(activeProjectId);
        }
      } catch (err) {
        console.error("Failed to save request", err);
      }
    }

    function autoSaveCurrentRequest() {
      saveCurrentRequest();
    }

    async function deleteCurrentRequest() {
      if (!activeRequestId) return;
      if (!confirm("Are you sure you want to delete this request?")) return;
      try {
        await fetch(`/api/requests/${activeRequestId}`, { method: "DELETE" });
        activeRequestId = null;
        showNoSelection();
        if (activeProjectId) {
          loadProjectRequests(activeProjectId);
        }
        showToast("Request deleted");
      } catch (err) {
        console.error("Failed to delete request", err);
      }
    }

    // Key-Value Table Helpers
    function populateKvTable(tbodyId, items) {
      const tbody = document.getElementById(tbodyId);
      tbody.innerHTML = "";
      if (!items || items.length === 0) {
        addKvRow(tbodyId);
        return;
      }
      items.forEach(item => addKvRow(tbodyId, item.key, item.value, item.enabled !== false));
    }

    function addKvRow(tbodyId, key = "", value = "", enabled = true) {
      const tbody = document.getElementById(tbodyId);
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td style="text-align: center;"><input type="checkbox" ${enabled ? 'checked' : ''} onchange="autoSaveCurrentRequest()"></td>
        <td><input type="text" placeholder="Key" value="${escapeHtml(key)}" onchange="autoSaveCurrentRequest()"></td>
        <td><input type="text" placeholder="Value" value="${escapeHtml(value)}" onchange="autoSaveCurrentRequest()"></td>
        <td>
          <button class="btn-icon" title="Remove" onclick="this.closest('tr').remove(); autoSaveCurrentRequest();">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
          </button>
        </td>
      `;
      tbody.appendChild(tr);
    }

    function readKvTable(tbodyId) {
      const rows = document.querySelectorAll(`#${tbodyId} tr`);
      const result = [];
      rows.forEach(r => {
        const checkbox = r.querySelector('input[type="checkbox"]');
        const inputs = r.querySelectorAll('input[type="text"]');
        if (inputs.length >= 2) {
          const k = inputs[0].value.trim();
          const v = inputs[1].value.trim();
          if (k || v) {
            result.push({
              key: k,
              value: v,
              enabled: checkbox ? checkbox.checked : true
            });
          }
        }
      });
      return result;
    }

    // Tabs & Body Switcher
    function switchReqTab(tabName) {
      document.querySelectorAll(".request-builder .tab-btn").forEach(b => b.classList.remove("active"));
      document.querySelectorAll(".request-builder .tab-pane").forEach(p => p.classList.remove("active"));

      const targetPane = document.getElementById(`tab-${tabName}`);
      if (targetPane) targetPane.classList.add("active");
      event.target.classList.add("active");
    }

    function toggleBodyType(type) {
      document.getElementById("bodyTypeNone").style.display = type === "none" ? "block" : "none";
      document.getElementById("bodyTypeJson").style.display = type === "raw_json" ? "block" : "none";
      document.getElementById("bodyTypeFormData").style.display = type === "form_data" ? "block" : "none";
      autoSaveCurrentRequest();
    }

    function beautifyJsonBody() {
      const area = document.getElementById("bodyRawJson");
      try {
        const parsed = JSON.parse(area.value);
        area.value = JSON.stringify(parsed, null, 2);
        autoSaveCurrentRequest();
        showToast("JSON formatted");
      } catch (e) {
        alert("Invalid JSON: " + e.message);
      }
    }

    function switchRespTab(tabName) {
      document.querySelectorAll(".response-header .tab-btn").forEach(b => b.classList.remove("active"));
      event.target.classList.add("active");

      document.getElementById("resp-tab-body").style.display = tabName === "body" ? "block" : "none";
      document.getElementById("resp-tab-headers").style.display = tabName === "headers" ? "block" : "none";
    }

    // Request Execution
    function handleUrlKeydown(e) {
      if (e.key === "Enter") {
        e.preventDefault();
        runRequest();
      }
    }

    async function runRequest() {
      const btn = document.getElementById("btnRun");
      const reqData = getFormDataFromUi();
      reqData.project_id = activeProjectId;

      const proj = projects.find(p => p.id === activeProjectId);
      if (proj) reqData.base_url = proj.base_url;

      btn.disabled = true;
      btn.innerHTML = `<span class="spinner"></span> <span>Running...</span>`;

      const metricsEl = document.getElementById("responseMetrics");
      metricsEl.innerHTML = `<span style="color: var(--text-muted);">Executing HTTP request...</span>`;

      try {
        const res = await fetch("/api/execute", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(reqData)
        });
        const data = await res.json();
        renderResponse(data);
      } catch (err) {
        metricsEl.innerHTML = `<span class="status-badge status-0">Error</span>`;
        document.getElementById("responseBodyDisplay").textContent = "Request execution failed: " + err.message;
      } finally {
        btn.disabled = false;
        btn.innerHTML = `<span>Run</span>`;
      }
    }

    function renderResponse(res) {
      const metricsEl = document.getElementById("responseMetrics");
      const bodyEl = document.getElementById("responseBodyDisplay");
      const headersTbody = document.getElementById("respHeadersTableBody");
      const headersCountEl = document.getElementById("respHeadersCount");

      let statusClass = "status-0";
      const code = res.status_code || 0;
      if (code >= 200 && code < 300) statusClass = "status-2xx";
      else if (code >= 300 && code < 400) statusClass = "status-3xx";
      else if (code >= 400 && code < 500) statusClass = "status-4xx";
      else if (code >= 500) statusClass = "status-5xx";

      const sizeStr = res.size_bytes !== undefined ? formatBytes(res.size_bytes) : "0 B";
      const durationStr = res.duration_ms !== undefined ? `${res.duration_ms} ms` : "0 ms";

      metricsEl.innerHTML = `
        <span class="status-badge ${statusClass}">${code} ${escapeHtml(res.status_text || '')}</span>
        <span style="color: #60a5fa;" title="Response Duration">⚡ ${durationStr}</span>
        <span style="color: #94a3b8;" title="Response Size">📦 ${sizeStr}</span>
      `;

      if (res.error) {
        currentRawResponse = res.error;
        bodyEl.innerHTML = `<span style="color: #f87171;">${escapeHtml(res.error)}</span>`;
      } else if (res.is_json && res.body !== null) {
        currentRawResponse = JSON.stringify(res.body, null, 2);
        bodyEl.innerHTML = syntaxHighlightJson(currentRawResponse);
      } else {
        currentRawResponse = res.raw_text || "";
        bodyEl.textContent = currentRawResponse || "(Empty Response Body)";
      }

      headersTbody.innerHTML = "";
      if (res.headers && res.headers.length > 0) {
        headersCountEl.textContent = `(${res.headers.length})`;
        res.headers.forEach(h => {
          const tr = document.createElement("tr");
          tr.innerHTML = `
            <td style="color: #93c5fd; font-family: var(--font-mono); font-size: 0.8rem;">${escapeHtml(h.key)}</td>
            <td style="font-family: var(--font-mono); font-size: 0.8rem; word-break: break-all;">${escapeHtml(h.value)}</td>
          `;
          headersTbody.appendChild(tr);
        });
      } else {
        headersCountEl.textContent = "";
        headersTbody.innerHTML = `<tr><td colspan="2" style="color: var(--text-muted); padding: 12px;">No response headers received.</td></tr>`;
      }
    }

    function copyResponseBody() {
      if (!currentRawResponse) return;
      navigator.clipboard.writeText(currentRawResponse);
      showToast("Response copied to clipboard");
    }

    function formatBytes(bytes) {
      if (bytes === 0) return "0 B";
      const k = 1024;
      const sizes = ["B", "KB", "MB", "GB"];
      const i = Math.floor(Math.log(bytes) / Math.log(k));
      return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + " " + sizes[i];
    }

    function syntaxHighlightJson(jsonStr) {
      jsonStr = escapeHtml(jsonStr);
      return jsonStr.replace(/("(\\\\u[a-zA-Z0-9]{4}|\\\\[^u]|[^\\\\"])*"(\\s*:)?|\\b(true|false|null)\\b|-?\\d+(?:\\.\\d*)?(?:[eE][+\\-]?\\d+)?)/g, function (match) {
        let cls = 'json-number';
        if (/^"/.test(match)) {
          if (/:$/.test(match)) {
            cls = 'json-key';
          } else {
            cls = 'json-string';
          }
        } else if (/true|false/.test(match)) {
          cls = 'json-boolean';
        } else if (/null/.test(match)) {
          cls = 'json-null';
        }
        return '<span class="' + cls + '">' + match + '</span>';
      });
    }

    function escapeHtml(str) {
      if (str === null || str === undefined) return "";
      return String(str)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
    }

    // Modal: Project
    function openNewProjectModal() {
      document.getElementById("projectNameInput").value = "";
      document.getElementById("projectBaseUrlInput").value = "";
      document.getElementById("projectModal").classList.add("show");
      document.getElementById("projectNameInput").focus();
    }

    function closeProjectModal() {
      document.getElementById("projectModal").classList.remove("show");
    }

    async function submitProjectModal() {
      const name = document.getElementById("projectNameInput").value.trim();
      const baseUrl = document.getElementById("projectBaseUrlInput").value.trim();
      if (!name) {
        alert("Please enter a project name.");
        return;
      }

      try {
        const res = await fetch("/api/projects", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name: name, base_url: baseUrl })
        });
        const newProj = await res.json();
        closeProjectModal();
        await loadProjects();
        selectProject(newProj.id);
        switchMainView('client');
        showToast("Project created");
      } catch (err) {
        console.error("Failed to create project", err);
      }
    }

    // Modal: Import Collection
    function openImportModal() {
      document.getElementById("importFileInput").value = "";
      document.getElementById("importJsonInput").value = "";
      document.getElementById("importModal").classList.add("show");
      document.getElementById("importJsonInput").focus();
    }

    function closeImportModal() {
      document.getElementById("importModal").classList.remove("show");
    }

    function handleImportFileSelect(e) {
      const file = e.target.files[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = function(evt) {
        document.getElementById("importJsonInput").value = evt.target.result;
      };
      reader.readAsText(file);
    }

    async function submitImport() {
      const text = document.getElementById("importJsonInput").value.trim();
      if (!text) {
        alert("Please select a file or paste JSON collection text.");
        return;
      }

      let parsedData = null;
      try {
        parsedData = JSON.parse(text);
      } catch (e) {
        alert("Invalid JSON format: " + e.message);
        return;
      }

      const btn = document.getElementById("btnSubmitImport");
      btn.disabled = true;
      btn.innerHTML = `<span class="spinner"></span> Importing...`;

      try {
        const res = await fetch("/api/import", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(parsedData)
        });
        const data = await res.json();
        if (data.error) {
          alert("Import failed: " + data.error);
        } else {
          closeImportModal();
          await loadProjects();
          if (data.project && data.project.id) {
            selectProject(data.project.id);
          }
          switchMainView('client');
          showToast(`Imported "${data.project.name}" (${data.imported_count} requests)`);
        }
      } catch (err) {
        alert("Import request error: " + err.message);
      } finally {
        btn.disabled = false;
        btn.innerHTML = "Import Collection";
      }
    }

    // Docs Helpers
    function copyPromptText() {
      const prompt = document.getElementById("aiPromptText").innerText;
      navigator.clipboard.writeText(prompt);
      showToast("AI Prompt copied to clipboard!");
    }

    function copySampleJson() {
      const sample = document.getElementById("sampleJsonText").innerText;
      navigator.clipboard.writeText(sample);
      showToast("Sample JSON copied to clipboard!");
    }

    async function importSampleDirectly() {
      const sample = document.getElementById("sampleJsonText").innerText;
      try {
        const parsed = JSON.parse(sample);
        const res = await fetch("/api/import", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(parsed)
        });
        const data = await res.json();
        await loadProjects();
        if (data.project && data.project.id) {
          selectProject(data.project.id);
        }
        switchMainView('client');
        showToast("Sample collection imported successfully!");
      } catch (e) {
        alert("Failed to import sample: " + e.message);
      }
    }
  </script>
</body>
</html>
"""

@app.route("/")
def index():
    return render_template_string(HTML_TEMPLATE)

# ==============================================================================
# Initialization & Runner
# ==============================================================================
def init_db():
    with app.app_context():
        db.create_all()

if __name__ == "__main__":
    init_db()
    print("=" * 60)
    print("  PostMini API Client running at http://127.0.0.1:5000")
    print("=" * 60)
    app.run(host="127.0.0.1", port=5000, debug=True)
