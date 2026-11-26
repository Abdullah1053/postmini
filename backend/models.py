import json
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

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
