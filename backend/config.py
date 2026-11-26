import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "postmini.db")

class Config:
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{DB_PATH}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")
    TEMPLATE_DIR = os.path.join(FRONTEND_DIR, "templates")
    STATIC_DIR = os.path.join(FRONTEND_DIR, "static")
