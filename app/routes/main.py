"""
GeoZones — Main routes
Homepage, neighborhood browsing, and serving user sites.
"""
from flask import Blueprint, render_template, abort, request, redirect, url_for, current_app, send_file
from app import db

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def index():
    from app.models import Site
    from sqlalchemy import desc
    featured  = Site.query.filter_by(status="approved").order_by(desc(Site.hit_count)).limit(12).all()
    newest    = Site.query.filter_by(status="approved").order_by(desc(Site.created_at)).limit(12).all()
    total     = Site.query.filter_by(status="approved").count()
    return render_template("main/index.html", featured=featured, newest=newest, total=total)


@main_bp.route("/neighborhoods/")
def neighborhoods():
    from app.models import Site
    hoods = current_app.config["NEIGHBORHOODS"]
    counts = {}
    for hood in hoods:
        counts[hood["slug"]] = Site.query.filter_by(
            neighborhood=hood["slug"], status="approved"
        ).count()
    return render_template("neighborhoods/index.html", hoods=hoods, counts=counts)


@main_bp.route("/neighborhoods/<neighborhood>/")
def neighborhood(neighborhood):
    from app.models import Site
    from sqlalchemy import desc
    hood = next((h for h in current_app.config["NEIGHBORHOODS"] if h["slug"] == neighborhood), None)
    if not hood:
        abort(404)
    page  = request.args.get("page", 1, type=int)
    sites = Site.query.filter_by(
        neighborhood=neighborhood, status="approved"
    ).order_by(desc(Site.hit_count)).paginate(page=page, per_page=24, error_out=False)
    return render_template("neighborhoods/view.html", hood=hood, sites=sites)


@main_bp.route("/<neighborhood>/<site_name>/")
@main_bp.route("/<neighborhood>/<site_name>/<path:filepath>")
def serve_site(neighborhood, site_name, filepath=None):
    """Serve a user's site files."""
    from app.models import Site, SiteFile
    import os, mimetypes

    site = Site.query.filter_by(name=site_name, neighborhood=neighborhood).first_or_404()

    if site.status != "approved":
        return render_template("sites/not_approved.html", site=site), 403

    # Increment hit counter (once per session per site)
    from flask import session
    hit_key = f"hit_{site.id}"
    if not session.get(hit_key):
        site.hit_count += 1
        db.session.commit()
        session[hit_key] = True

    # Default to index.html
    if not filepath:
        filepath = "index.html"

    # Find the file
    site_file = SiteFile.query.filter_by(site_id=site.id, filename=filepath).first()

    if not site_file:
        # Try index.html for directory requests
        if not filepath.endswith("/"):
            site_file = SiteFile.query.filter_by(
                site_id=site.id, filename=filepath + "/index.html"
            ).first()

    if not site_file or not os.path.exists(site_file.path):
        # Custom 404 page
        custom_404 = SiteFile.query.filter_by(site_id=site.id, filename="404.html").first()
        if custom_404 and os.path.exists(custom_404.path):
            return send_file(custom_404.path), 404
        return render_template("sites/404.html", site=site), 404

    mime_type = site_file.mime_type or mimetypes.guess_type(filepath)[0] or "application/octet-stream"
    return send_file(site_file.path, mimetype=mime_type)


@main_bp.route("/search")
def search():
    from app.models import Site
    from sqlalchemy import desc
    q    = request.args.get("q", "").strip()
    hood = request.args.get("neighborhood", "")
    page = request.args.get("page", 1, type=int)

    query = Site.query.filter_by(status="approved")
    if q:
        query = query.filter(
            (Site.title.ilike(f"%{q}%")) |
            (Site.description.ilike(f"%{q}%")) |
            (Site.name.ilike(f"%{q}%"))
        )
    if hood:
        query = query.filter_by(neighborhood=hood)

    results = query.order_by(desc(Site.hit_count)).paginate(
        page=page, per_page=20, error_out=False
    )
    return render_template("main/search.html", results=results, q=q, hood=hood)


# ─── Web ring navigation ──────────────────────────────────────
@main_bp.route("/webring/<ring_slug>/next/<int:site_id>")
def webring_next(ring_slug, site_id):
    from app.models import WebRing, WebRingMember
    ring = WebRing.query.filter_by(slug=ring_slug).first_or_404()
    members = ring.members
    if not members:
        abort(404)
    positions = [m.site_id for m in members]
    try:
        idx = positions.index(site_id)
        next_site = members[(idx + 1) % len(members)].site
    except ValueError:
        next_site = members[0].site
    return redirect(f"/{next_site.neighborhood}/{next_site.name}/")


@main_bp.route("/webring/<ring_slug>/prev/<int:site_id>")
def webring_prev(ring_slug, site_id):
    from app.models import WebRing, WebRingMember
    ring = WebRing.query.filter_by(slug=ring_slug).first_or_404()
    members = ring.members
    if not members:
        abort(404)
    positions = [m.site_id for m in members]
    try:
        idx = positions.index(site_id)
        prev_site = members[(idx - 1) % len(members)].site
    except ValueError:
        prev_site = members[-1].site
    return redirect(f"/{prev_site.neighborhood}/{prev_site.name}/")


@main_bp.route("/webring/<ring_slug>/random")
def webring_random(ring_slug):
    from app.models import WebRing
    import random
    ring = WebRing.query.filter_by(slug=ring_slug).first_or_404()
    if not ring.members:
        abort(404)
    site = random.choice(ring.members).site
    return redirect(f"/{site.neighborhood}/{site.name}/")
