"""Settings API — manage API keys and preferences.

Handles CRUD for API keys with auto-validation against respective services.
Genius keys support 4 slots with automatic round-robin rotation.
"""
import time

from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user

from app.database import Session, ApiKey, LifetimeStats

settings_bp = Blueprint("settings", __name__, url_prefix="/api/settings")


@settings_bp.route("/keys", methods=["GET"])
@login_required
def get_keys():
    """Return all API key slots with masked values and validation status."""
    session = Session()
    try:
        keys = session.query(ApiKey).filter_by(user_id=current_user.id).all()
        result = {}
        for k in keys:
            slot_id = f"{k.service}_{k.slot}" if k.service == "genius" else k.service
            result[slot_id] = {
                "set": True,
                "valid": k.is_valid,
                "masked": k.masked(),
                "service": k.service,
                "slot": k.slot,
            }
        return jsonify({"keys": result})
    finally:
        Session.remove()


@settings_bp.route("/keys", methods=["POST"])
@login_required
def save_key():
    """Save or update an API key. Validates against the respective service."""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Invalid body"}), 400

    service = data.get("service", "").strip().lower()
    slot = int(data.get("slot", 1))
    key_value = (data.get("key") or "").strip()

    if not service or not key_value:
        return jsonify({"error": "service and key required"}), 400

    valid_services = {"genius", "groq", "gemini"}
    if service not in valid_services:
        return jsonify({"error": f"service must be one of: {valid_services}"}), 400

    if service == "genius" and not (1 <= slot <= 4):
        return jsonify({"error": "Genius slot must be 1-4"}), 400

    # Validate the key
    is_valid = _validate_key(service, key_value)

    session = Session()
    try:
        existing = session.query(ApiKey).filter_by(
            user_id=current_user.id, service=service, slot=slot
        ).first()

        if existing:
            existing.key_value = key_value
            existing.is_valid = is_valid
            existing.last_validated = time.time()
        else:
            new_key = ApiKey(
                user_id=current_user.id,
                service=service,
                slot=slot,
                key_value=key_value,
                is_valid=is_valid,
                last_validated=time.time(),
            )
            session.add(new_key)

        session.commit()

        # Also update the legacy keys store so existing tools still work
        _sync_to_legacy_keys(service, slot, key_value, session)

        slot_id = f"{service}_{slot}" if service == "genius" else service
        return jsonify({
            "ok": True,
            "valid": is_valid,
            "masked": "•" * 8 + key_value[-4:] if len(key_value) > 4 else "****",
            "slot_id": slot_id,
        })
    except Exception as e:
        session.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        Session.remove()


def _validate_key(service: str, key: str) -> bool:
    """Test a key against its service API. Returns True if valid."""
    import requests as http

    try:
        if service == "genius":
            r = http.get(
                "https://api.genius.com/search",
                params={"q": "test", "per_page": 1},
                headers={"Authorization": f"Bearer {key}"},
                timeout=8,
            )
            return r.status_code == 200

        elif service == "groq":
            r = http.get(
                "https://api.groq.com/openai/v1/models",
                headers={"Authorization": f"Bearer {key}"},
                timeout=8,
            )
            return r.status_code == 200

        elif service == "gemini":
            r = http.get(
                f"https://generativelanguage.googleapis.com/v1/models?key={key}",
                timeout=8,
            )
            return r.status_code == 200

    except Exception:
        pass
    return False


def _sync_to_legacy_keys(service: str, slot: int, key_value: str, session):
    """Sync new API key to the legacy keys.json store so existing tools work."""
    from app import config

    store = config.keys_store()
    if service == "genius" and slot == 1:
        store.set("genius_token", key_value)
    elif service == "groq":
        store.set("groq_api_key", key_value)
    elif service == "gemini":
        store.set("gemini_api_key", key_value)


# ---------------------------------------------------------------------------
# Stats endpoint for dashboard widgets
# ---------------------------------------------------------------------------

@settings_bp.route("/keys/genius/active", methods=["GET"])
@login_required
def genius_active_key():
    """Return the currently active Genius key (for rotation display)."""
    session = Session()
    try:
        keys = session.query(ApiKey).filter_by(
            user_id=current_user.id, service="genius", is_valid=True
        ).order_by(ApiKey.requests_today.asc()).all()
        if keys:
            return jsonify({"active_slot": keys[0].slot, "total_keys": len(keys)})
        return jsonify({"active_slot": None, "total_keys": 0})
    finally:
        Session.remove()
