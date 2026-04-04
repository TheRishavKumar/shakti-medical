from flask import Flask, render_template
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from config import Config

db = SQLAlchemy()
login_manager = LoginManager()

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "main.login"

    from app.models import User

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    from app.routes import main
    app.register_blueprint(main)

    with app.app_context():
        db.create_all()

    # ── Error Handlers ──────────────────────────
    @app.errorhandler(404)
    def not_found(e):
        return render_template('error.html',
                               message="Page not found. It may have been moved or deleted."), 404

    @app.errorhandler(500)
    def server_error(e):
        return render_template('error.html',
                               message="Something went wrong on our end. Please restart the app."), 500

    @app.errorhandler(403)
    def forbidden(e):
        return render_template('error.html',
                               message="You don't have permission to access this page."), 403

    return app