"""Authentication routes — login, logout, session check.

Uses Flask-Login for session management with secure HTTP-only cookies.
"""
from flask import Blueprint, request, jsonify
from flask_login import LoginManager, login_user, logout_user, current_user, login_required, UserMixin

from app.database import Session, User

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")

# Flask-Login setup
login_manager = LoginManager()
login_manager.session_protection = "basic"


@login_manager.unauthorized_handler
def unauthorized():
    """Return 401 JSON instead of redirecting — fixes login after logout."""
    return jsonify({"error": "Not authenticated"}), 401


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
    totp_code = data.get("totp_code", "").strip()

    if not email or not password:
        return jsonify({"error": "Email and password required"}), 400

    session = Session()
    try:
        user = session.query(User).filter_by(email=email).first()
        if not user or not user.check_password(password):
            return jsonify({"error": "Invalid email or password"}), 401

        # Check 2FA if enabled
        if user.totp_enabled:
            if not totp_code:
                return jsonify({"error": "2FA code required", "requires_2fa": True}), 401
            import pyotp
            totp = pyotp.TOTP(user.totp_secret)
            if not totp.verify(totp_code, valid_window=1):
                return jsonify({"error": "Invalid 2FA code", "requires_2fa": True}), 401

        auth_user = AuthUser(user)
        login_user(auth_user, remember=True)
        return jsonify({"user": user.to_dict()})
    finally:
        Session.remove()


@auth_bp.route("/logout", methods=["POST"])
def logout():
    logout_user()
    return jsonify({"ok": True})


@auth_bp.route("/me")
def me():
    if not current_user.is_authenticated:
        return jsonify({"error": "Not authenticated"}), 401
    return jsonify({"user": current_user.to_dict()})



# ---------------------------------------------------------------------------
# Two-Factor Authentication (TOTP via Google Authenticator)
# ---------------------------------------------------------------------------

@auth_bp.route("/2fa/setup", methods=["POST"])
@login_required
def setup_2fa():
    """Generate a TOTP secret and return the provisioning URI + QR code."""
    import pyotp
    import qrcode
    import io
    import base64

    session = Session()
    try:
        user = session.query(User).get(current_user.id)
        if user.totp_enabled:
            return jsonify({"error": "2FA already enabled"}), 400

        # Generate secret
        secret = pyotp.random_base32()
        user.totp_secret = secret
        session.commit()

        # Generate provisioning URI
        totp = pyotp.TOTP(secret)
        uri = totp.provisioning_uri(name=user.email, issuer_name="IGNITE Virtual Scout")

        # Generate QR code as base64
        img = qrcode.make(uri)
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        qr_b64 = base64.b64encode(buf.getvalue()).decode('utf-8')

        return jsonify({
            "secret": secret,
            "uri": uri,
            "qr": f"data:image/png;base64,{qr_b64}",
        })
    finally:
        Session.remove()


@auth_bp.route("/2fa/verify", methods=["POST"])
@login_required
def verify_2fa():
    """Verify a TOTP code and enable 2FA if correct."""
    import pyotp

    data = request.get_json(silent=True) or {}
    code = data.get("code", "").strip()
    if not code:
        return jsonify({"error": "Code required"}), 400

    session = Session()
    try:
        user = session.query(User).get(current_user.id)
        if not user.totp_secret:
            return jsonify({"error": "Setup 2FA first"}), 400

        totp = pyotp.TOTP(user.totp_secret)
        if totp.verify(code, valid_window=1):
            user.totp_enabled = True
            session.commit()
            return jsonify({"ok": True, "message": "2FA enabled"})
        else:
            return jsonify({"error": "Invalid code"}), 401
    finally:
        Session.remove()


@auth_bp.route("/2fa/disable", methods=["POST"])
@login_required
def disable_2fa():
    """Disable 2FA for the current user."""
    session = Session()
    try:
        user = session.query(User).get(current_user.id)
        user.totp_enabled = False
        user.totp_secret = None
        session.commit()
        return jsonify({"ok": True})
    finally:
        Session.remove()
