import json
from flask import Blueprint, request, jsonify
from backend.models import db, Project, ApiRequest
from backend.services.executor import execute_http_request
from backend.services.importer import parse_collection_payload

api_bp = Blueprint("api", __name__, url_prefix="/api")

# --- Projects Endpoints ---
@api_bp.route("/projects", methods=["GET"])
def get_projects():
    projects = Project.query.order_by(Project.created_at.desc()).all()
    return jsonify([p.to_dict() for p in projects])

@api_bp.route("/projects", methods=["POST"])
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

@api_bp.route("/projects/<int:project_id>", methods=["PUT"])
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

@api_bp.route("/projects/<int:project_id>", methods=["DELETE"])
def delete_project(project_id):
    project = db.session.get(Project, project_id)
    if not project:
        return jsonify({"error": "Project not found"}), 404
    db.session.delete(project)
    db.session.commit()
    return jsonify({"success": True})

# --- Requests Endpoints ---
@api_bp.route("/projects/<int:project_id>/requests", methods=["GET"])
def get_project_requests(project_id):
    project = db.session.get(Project, project_id)
    if not project:
        return jsonify({"error": "Project not found"}), 404
    reqs = ApiRequest.query.filter_by(project_id=project_id).order_by(ApiRequest.id.asc()).all()
    return jsonify([r.to_dict() for r in reqs])

@api_bp.route("/projects/<int:project_id>/requests", methods=["POST"])
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

@api_bp.route("/requests/<int:req_id>", methods=["GET"])
def get_request_detail(req_id):
    req_item = db.session.get(ApiRequest, req_id)
    if not req_item:
        return jsonify({"error": "Request not found"}), 404
    return jsonify(req_item.to_dict())

@api_bp.route("/requests/<int:req_id>", methods=["PUT"])
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

@api_bp.route("/requests/<int:req_id>", methods=["DELETE"])
def delete_request_detail(req_id):
    req_item = db.session.get(ApiRequest, req_id)
    if not req_item:
        return jsonify({"error": "Request not found"}), 404
    db.session.delete(req_item)
    db.session.commit()
    return jsonify({"success": True})

# --- Collection Import ---
@api_bp.route("/import", methods=["POST"])
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

# --- Execution Engine ---
@api_bp.route("/execute", methods=["POST"])
def execute_request():
    data = request.get_json() or {}
    base_url = data.get("base_url", "")
    project_id = data.get("project_id")

    if not base_url and project_id:
        proj = db.session.get(Project, project_id)
        if proj:
            base_url = proj.base_url

    res, code = execute_http_request(data, base_url=base_url)
    return jsonify(res), code
