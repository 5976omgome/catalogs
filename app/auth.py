"""Authentication routes — login, logout, session check.

Uses Flask-Login for session management with secure HTTP-only cookies.
"""
from flask import Blueprint, request, jsonify
from flask_login import LoginManager, login_user, logout_user, current_user, login_required, UserMixin

from app.database import Session, User

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")

# Flask-Login setup
login_manager = LoginManager()
login_manager.session_protection = "strong"


class AuthUser(UserMixin):
    """Wrapper to make SQLAlchemy User work with Flask-Login."""

    def __init__(self, user: User):
        self.id = user.id
        self.email = user.email
        self.name = user.name
        self.role = user.role
        self.timezone = user.timezone
        self._user = user

    def get_id(self):
        return str(self.id)

    def to_dict(self):
        return self._user.to_dict()


@login_manager.user_loader
def load_user(user_id):
    session = Session()
    try:
        user = session.query(User).get(int(user_id))
        if user:
            return AuthUser(user)
    finally:
        Session.remove()
    return None


@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Invalid request"}), 400

    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not email or not password:
        return jsonify({"error": "Email and password required"}), 400

    session = Session()
    try:
        user = session.query(User).filter_by(email=email).first()
        if not user or not user.check_password(password):
            return jsonify({"error": "Invalid email or password"}), 401

        auth_user = AuthUser(user)
        login_user(auth_user, remember=True)
        return jsonify({"user": user.to_dict()})
    finally:
        Session.remove()


@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    return jsonify({"ok": True})


@auth_bp.route("/me")
def me():
    if not current_user.is_authenticated:
        return jsonify({"error": "Not authenticated"}), 401
    return jsonify({"user": current_user.to_dict()})
