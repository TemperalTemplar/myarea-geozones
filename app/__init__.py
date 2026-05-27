"""
GeoZones — GeoCities-style personal web hosting
Part of the MyArea platform.
"""
import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from flask_migrate import Migrate
from authlib.integrations.flask_client import OAuth

db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()
migrate = Migrate()
oauth = OAuth()


def create_app() -> Flask:
    app = Flask(__name__, template_folder="templates", static_folder="static")

    app.config.update(
        SECRET_KEY=os.getenv("SECRET_KEY", "change-me"),
        SQLALCHEMY_DATABASE_URI=os.getenv("DATABASE_URL", "sqlite:///geozones.db"),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SQLALCHEMY_ENGINE_OPTIONS={"pool_pre_ping": True, "pool_recycle": 300},

        # File storage
        UPLOAD_FOLDER=os.getenv("UPLOAD_FOLDER", "/app/uploads"),
        MAX_STORAGE_MB=int(os.getenv("MAX_STORAGE_MB", 150)),
        MAX_CONTENT_LENGTH=int(os.getenv("MAX_STORAGE_MB", 150)) * 1024 * 1024,
        ALLOWED_EXTENSIONS={
            "html", "htm", "css", "js", "txt", "xml",
            "jpg", "jpeg", "png", "gif", "webp", "ico", "bmp",
            "mp3", "wav", "mid", "midi", "ogg",
            "mp4", "webm",
            "pdf", "zip",
            "woff", "woff2", "ttf", "eot",
        },
        BLOCKED_EXTENSIONS={"php", "py", "sh", "rb", "pl", "exe", "bat", "cmd"},

        # Cross-app
        SERVICE_API_KEY=os.getenv("SERVICE_API_KEY", ""),
        SOCIAL_APP_URL=os.getenv("SOCIAL_APP_URL", "https://myarea.wrds361.com"),
        MYAREA_API_URL=os.getenv("MYAREA_API_URL", "http://myarea_social_web:5000"),

        # OIDC
        OIDC_CLIENT_ID=os.getenv("OIDC_CLIENT_ID", ""),
        OIDC_CLIENT_SECRET=os.getenv("OIDC_CLIENT_SECRET", ""),
        OIDC_DISCOVERY_URL=os.getenv("OIDC_DISCOVERY_URL", ""),
        OIDC_REDIRECT_URI=os.getenv("OIDC_REDIRECT_URI", ""),

        # Neighborhoods
        NEIGHBORHOODS=[
            {"slug": "downtown",      "name": "Downtown",      "icon": "🏙️",  "desc": "Business, portfolios, professional sites"},
            {"slug": "entertainment", "name": "Entertainment", "icon": "🎬",  "desc": "Music, movies, TV, celebrity fan pages"},
            {"slug": "gaming",        "name": "Gaming",        "icon": "🎮",  "desc": "Game sites, clans, walkthroughs"},
            {"slug": "arts",          "name": "Arts & Poetry", "icon": "🎨",  "desc": "Art, poetry, creative writing, photography"},
            {"slug": "tech",          "name": "Silicon Valley","icon": "💻",  "desc": "Coding, tech projects, open source"},
            {"slug": "community",     "name": "Community",     "icon": "🤝",  "desc": "Clubs, organizations, causes"},
            {"slug": "heartland",     "name": "Heartland",     "icon": "🌾",  "desc": "Family, pets, hobbies, personal pages"},
            {"slug": "westwood",      "name": "Westwood",      "icon": "🎓",  "desc": "Education, schools, research"},
            {"slug": "area51",        "name": "Area 51",       "icon": "👽",  "desc": "Weird, wacky, unexplained, sci-fi"},
            {"slug": "colosseum",     "name": "Colosseum",     "icon": "⚔️",  "desc": "Sports, fitness, martial arts"},
            {"slug": "enchanted",     "name": "Enchanted Forest","icon": "🌲","desc": "Fantasy, RPG, mythology, magic"},
            {"slug": "neon",          "name": "Neon District",  "icon": "🌃", "desc": "Anime, manga, J-culture"},
        ],

        PREFERRED_URL_SCHEME=os.getenv("PREFERRED_URL_SCHEME", "https"),
    )

    # ProxyFix for Cloudflare
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)
    oauth.init_app(app)

    login_manager.login_view = "auth.login"
    login_manager.login_message = "Please log in to access GeoZones."
    login_manager.login_message_category = "warning"

    @login_manager.user_loader
    def load_user(user_id):
        from app.models import User
        return db.session.get(User, int(user_id))

    if app.config.get("OIDC_CLIENT_ID"):
        oauth.register(
            name="authentik",
            client_id=app.config["OIDC_CLIENT_ID"],
            client_secret=app.config["OIDC_CLIENT_SECRET"],
            server_metadata_url=app.config["OIDC_DISCOVERY_URL"],
            client_kwargs={"scope": "openid email profile"},
        )

    from app.routes.auth import auth_bp
    from app.routes.social import social_bp
    from app.routes.main import main_bp
    from app.routes.sites import sites_bp
    from app.routes.editor import editor_bp
    from app.routes.admin import admin_bp
    from app.routes.api import api_bp

    app.register_blueprint(auth_bp,   url_prefix="/auth")
    app.register_blueprint(main_bp,   url_prefix="/")
    app.register_blueprint(sites_bp,  url_prefix="/sites")
    app.register_blueprint(editor_bp, url_prefix="/editor")
    app.register_blueprint(admin_bp,  url_prefix="/admin")
    app.register_blueprint(api_bp,    url_prefix="/api")
    app.register_blueprint(social_bp, url_prefix="/social")

    @app.context_processor
    def inject_globals():
        from datetime import datetime, timezone
        from flask_login import current_user
        return dict(
            now=datetime.now(timezone.utc),
            neighborhoods=app.config["NEIGHBORHOODS"],
            config=app.config,
        )

    return app
