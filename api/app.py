from __future__ import annotations

from flask import Flask, jsonify
from flask_cors import CORS

from api.routes import api_bp
from config.logging import configure_logging
from config.settings import settings


def create_app() -> Flask:
    configure_logging()

    app = Flask(__name__)
    CORS(
        app,
        resources={r"/api/*": {"origins": settings.cors_origins_list}},
    )

    app.register_blueprint(api_bp, url_prefix="/api")

    @app.get("/")
    def index():
        return jsonify(
            {
                "name": "SPDB API",
                "health": "/api/health",
                "compare": "/api/routes/compare",
                "geocode": "/api/geocode/search",
            }
        )

    return app
