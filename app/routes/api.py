"""GeoZones — API (hit counter embed, webring widgets)"""
from flask import Blueprint, jsonify, request, current_app
api_bp = Blueprint("api", __name__)


@api_bp.route("/hit/<site_name>")
def hit_counter(site_name):
    """Increment and return hit count. Used by embedded counter widget."""
    from app.models import Site
    from app import db
    from flask import session
    site = Site.query.filter_by(name=site_name, status="approved").first()
    if not site:
        return jsonify({"count": 0})
    hit_key = f"hit_{site.id}"
    if not session.get(hit_key):
        site.hit_count += 1
        db.session.commit()
        session[hit_key] = True
    return jsonify({"count": site.hit_count, "name": site_name})


@api_bp.route("/webring-widget/<ring_slug>/<site_name>")
def webring_widget(ring_slug, site_name):
    """Returns HTML snippet for embedding a webring widget on a site."""
    from app.models import WebRing, Site
    ring = WebRing.query.filter_by(slug=ring_slug).first()
    site = Site.query.filter_by(name=site_name).first()
    if not ring or not site:
        return "<p>Invalid webring</p>"

    base = request.host_url.rstrip("/")
    html = f"""<div style="font-family:Arial;font-size:11px;text-align:center;border:1px solid #999;padding:4px;background:#000080;color:#fff;">
<b>{ring.name}</b><br>
<a href="{base}/webring/{ring_slug}/prev/{site.id}" style="color:#ffff00">&#9664; Prev</a>
&nbsp;|&nbsp;
<a href="{base}/webring/{ring_slug}/random" style="color:#ffff00">Random</a>
&nbsp;|&nbsp;
<a href="{base}/webring/{ring_slug}/next/{site.id}" style="color:#ffff00">Next &#9654;</a>
</div>"""
    return html


@api_bp.route("/site-by-sub/<oidc_sub>")
def site_by_sub(oidc_sub):
    """Return a user's site info by their Authentik oidc_sub. Used by MyArea social widget."""
    from flask import current_app
    from app.models import User, Site

    # Verify service key
    key = request.headers.get("X-Service-Key", "")
    if key != current_app.config.get("SERVICE_API_KEY", ""):
        return jsonify({"error": "Unauthorized"}), 403

    user = User.query.filter_by(oidc_sub=oidc_sub).first()
    if not user or not user.site or user.site.status != "approved":
        return jsonify({"found": False})

    site = user.site
    hood = next((h for h in current_app.config["NEIGHBORHOODS"] if h["slug"] == site.neighborhood), None)

    return jsonify({
        "found": True,
        "name": site.name,
        "title": site.title,
        "neighborhood": site.neighborhood,
        "neighborhood_name": hood["name"] if hood else site.neighborhood,
        "neighborhood_icon": hood["icon"] if hood else "🌐",
        "url": f"https://geozones.wrds361.com/{site.neighborhood}/{site.name}/",
        "guestbook_url": f"https://geozones.wrds361.com/sites/{site.name}/guestbook",
        "hit_count": site.hit_count,
        "follower_count": len(site.followers) if hasattr(site, "followers") else 0,
        "under_construction": site.under_construction,
    })
