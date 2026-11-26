from flask import Flask
from backend.config import Config
from backend.models import db
from backend.routes.api import api_bp
from backend.routes.views import views_bp

def create_app(config_class=Config):
    app = Flask(
        __name__,
        template_folder=config_class.TEMPLATE_DIR,
        static_folder=config_class.STATIC_DIR
    )
    app.config.from_object(config_class)

    db.init_app(app)

    # Register Blueprints
    app.register_blueprint(views_bp)
    app.register_blueprint(api_bp)

    with app.app_context():
        db.create_all()

    return app
