"""
GeoZones — Site management routes
Apply, manage settings, guestbook, file manager, web rings.
"""
import os
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app, abort
from flask_login import login_required, current_user
from app import db

sites_bp = Blueprint("sites", __name__)


def _site_upload_dir(site):
    base = current_app.config["UPLOAD_FOLDER"]
    path = os.path.join(base, "geozones", str(site.id))
    os.makedirs(path, exist_ok=True)
    return path


def _allowed_file(filename):
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    blocked = current_app.config["BLOCKED_EXTENSIONS"]
    allowed = current_app.config["ALLOWED_EXTENSIONS"]
    return ext not in blocked and ext in allowed


# ─── Apply for a site ─────────────────────────────────────────
@sites_bp.route("/apply", methods=["GET", "POST"])
@login_required
def apply():
    from app.models import SiteApplication, Site
    # Already has a site
    if current_user.site:
        return redirect(url_for("sites.dashboard"))
    # Already has pending application
    existing = SiteApplication.query.filter_by(
        user_id=current_user.id, status="pending"
    ).first()
    if existing:
        return render_template("sites/apply_pending.html", application=existing)

    if request.method == "POST":
        site_name    = request.form.get("site_name", "").strip().lower()
        site_title   = request.form.get("site_title", "").strip()
        neighborhood = request.form.get("neighborhood", "").strip()
        description  = request.form.get("description", "").strip()
        reason       = request.form.get("reason", "").strip()

        errors = []
        if len(site_name) < 2 or len(site_name) > 32:
            errors.append("Site name must be 2–32 characters.")
        if not site_name.replace("-", "").replace("_", "").isalnum():
            errors.append("Site name may only contain letters, numbers, hyphens, underscores.")
        if Site.query.filter_by(name=site_name).first():
            errors.append("That site name is already taken.")
        valid_hoods = [h["slug"] for h in current_app.config["NEIGHBORHOODS"]]
        if neighborhood not in valid_hoods:
            errors.append("Please select a valid neighborhood.")
        if not reason:
            errors.append("Please tell us what your site will be about.")

        if errors:
            for e in errors: flash(e, "danger")
            return render_template("sites/apply.html", form=request.form)

        app_obj = SiteApplication(
            user_id=current_user.id,
            site_name=site_name,
            site_title=site_title,
            neighborhood=neighborhood,
            description=description,
            reason=reason,
        )
        db.session.add(app_obj)
        db.session.commit()
        flash("Application submitted! An admin will review it shortly.", "success")
        return redirect(url_for("sites.apply"))

    return render_template("sites/apply.html", form={})


# ─── Site dashboard ───────────────────────────────────────────
@sites_bp.route("/dashboard")
@login_required
def dashboard():
    if not current_user.site:
        return redirect(url_for("sites.apply"))
    site = current_user.site
    return render_template("sites/dashboard.html", site=site)


# ─── File manager ─────────────────────────────────────────────
@sites_bp.route("/files")
@login_required
def files():
    if not current_user.site or current_user.site.status != "approved":
        abort(403)
    site = current_user.site
    return render_template("sites/files.html", site=site)


@sites_bp.route("/files/upload", methods=["POST"])
@login_required
def upload_file():
    from app.models import SiteFile
    if not current_user.site or current_user.site.status != "approved":
        abort(403)
    site = current_user.site

    if "file" not in request.files:
        flash("No file selected.", "danger")
        return redirect(url_for("sites.files"))

    file = request.files["file"]
    if not file.filename:
        flash("No file selected.", "danger")
        return redirect(url_for("sites.files"))

    filename = file.filename.replace("..", "").replace("/", "").replace("\\", "")

    if not _allowed_file(filename):
        flash(f"File type not allowed.", "danger")
        return redirect(url_for("sites.files"))

    # Check storage limit
    file.seek(0, 2)
    file_size = file.tell()
    file.seek(0)

    max_bytes = current_app.config["MAX_STORAGE_MB"] * 1024 * 1024
    if site.storage_used + file_size > max_bytes:
        flash(f"Storage limit reached ({current_app.config['MAX_STORAGE_MB']}MB max).", "danger")
        return redirect(url_for("sites.files"))

    upload_dir = _site_upload_dir(site)
    disk_path  = os.path.join(upload_dir, filename)
    file.save(disk_path)

    import mimetypes
    mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"

    # Update or create file record
    existing = SiteFile.query.filter_by(site_id=site.id, filename=filename).first()
    if existing:
        site.storage_used -= existing.size_bytes
        existing.size_bytes = file_size
        existing.path       = disk_path
        existing.mime_type  = mime
    else:
        sf = SiteFile(
            site_id=site.id, filename=filename,
            path=disk_path, mime_type=mime,
            size_bytes=file_size,
            is_index=(filename.lower() == "index.html"),
        )
        db.session.add(sf)

    site.storage_used += file_size
    db.session.commit()
    flash(f"Uploaded {filename}.", "success")
    return redirect(url_for("sites.files"))


@sites_bp.route("/files/delete/<int:file_id>", methods=["POST"])
@login_required
def delete_file(file_id):
    from app.models import SiteFile
    sf = SiteFile.query.get_or_404(file_id)
    if sf.site.user_id != current_user.id:
        abort(403)
    if os.path.exists(sf.path):
        os.remove(sf.path)
    sf.site.storage_used = max(0, sf.site.storage_used - sf.size_bytes)
    db.session.delete(sf)
    db.session.commit()
    flash(f"Deleted {sf.filename}.", "info")
    return redirect(url_for("sites.files"))


# ─── Guestbook ────────────────────────────────────────────────
@sites_bp.route("/<site_name>/guestbook", methods=["GET", "POST"])
def guestbook(site_name):
    from app.models import Site, GuestbookEntry
    from sqlalchemy import desc
    site = Site.query.filter_by(name=site_name, status="approved").first_or_404()

    if request.method == "POST":
        author_name = request.form.get("name", "").strip()[:64]
        author_url  = request.form.get("url", "").strip()[:256]
        message     = request.form.get("message", "").strip()[:1000]
        if not author_name or not message:
            flash("Name and message are required.", "danger")
        else:
            entry = GuestbookEntry(
                site_id=site.id,
                author_name=author_name,
                author_url=author_url or None,
                message=message,
            )
            db.session.add(entry)
            db.session.commit()
            try:
                from flask_login import current_user as _cu
                signer_is_owner = (_cu.is_authenticated and _cu.id == site.user_id)
                if not signer_is_owner:
                    from app.notify import notify_user
                    notify_user(site.user_id, "guestbook_signed",
                        "New guestbook signature",
                        f'{author_name} signed your guestbook on {site.name}.',
                        f"https://geozones.wrds361.com/sites/{site.name}/guestbook")
            except Exception:
                pass
            flash("Thanks for signing the guestbook!", "success")
        return redirect(url_for("sites.guestbook", site_name=site_name))

    entries = GuestbookEntry.query.filter_by(
        site_id=site.id, is_approved=True
    ).order_by(desc(GuestbookEntry.created_at)).limit(50).all()
    return render_template("sites/guestbook.html", site=site, entries=entries)


@sites_bp.route("/guestbook/delete/<int:entry_id>", methods=["POST"])
@login_required
def delete_guestbook_entry(entry_id):
    from app.models import GuestbookEntry
    entry = GuestbookEntry.query.get_or_404(entry_id)
    if entry.site.user_id != current_user.id and not current_user.is_admin:
        abort(403)
    db.session.delete(entry)
    db.session.commit()
    flash("Entry deleted.", "info")
    return redirect(url_for("sites.guestbook", site_name=entry.site.name))


# ─── Settings ─────────────────────────────────────────────────
@sites_bp.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    if not current_user.site:
        abort(404)
    site = current_user.site
    if request.method == "POST":
        site.title       = request.form.get("title", site.title).strip()[:128]
        site.description = request.form.get("description", "").strip()[:500]
        site.bg_color    = request.form.get("bg_color", site.bg_color)
        site.text_color  = request.form.get("text_color", site.text_color)
        site.link_color  = request.form.get("link_color", site.link_color)
        site.under_construction = bool(request.form.get("under_construction"))
        db.session.commit()
        flash("Settings saved.", "success")
        return redirect(url_for("sites.settings"))
    return render_template("sites/settings.html", site=site)


# ─── Web rings ────────────────────────────────────────────────
@sites_bp.route("/webrings")
def webrings():
    from app.models import WebRing
    from sqlalchemy import desc
    rings = WebRing.query.order_by(desc(WebRing.created_at)).all()
    return render_template("sites/webrings.html", rings=rings)


@sites_bp.route("/webrings/create", methods=["GET", "POST"])
@login_required
def create_webring():
    from app.models import WebRing
    from slugify import slugify
    if not current_user.site or current_user.site.status != "approved":
        flash("You need an approved site to create a web ring.", "danger")
        return redirect(url_for("sites.webrings"))

    if request.method == "POST":
        name        = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip()
        neighborhood= request.form.get("neighborhood", "").strip() or None
        slug        = slugify(name)

        if WebRing.query.filter_by(slug=slug).first():
            flash("A ring with that name already exists.", "danger")
            return render_template("sites/webring_create.html")

        ring = WebRing(name=name, slug=slug, description=description,
                       neighborhood=neighborhood, owner_id=current_user.id)
        db.session.add(ring)
        db.session.commit()

        # Auto-join as first member
        from app.models import WebRingMember
        member = WebRingMember(ring_id=ring.id, site_id=current_user.site.id, position=0)
        db.session.add(member)
        db.session.commit()

        flash(f"Web ring '{name}' created!", "success")
        return redirect(url_for("sites.webrings"))

    return render_template("sites/webring_create.html")


@sites_bp.route("/webrings/<ring_slug>/join", methods=["POST"])
@login_required
def join_webring(ring_slug):
    from app.models import WebRing, WebRingMember
    if not current_user.site or current_user.site.status != "approved":
        flash("You need an approved site to join a web ring.", "danger")
        return redirect(url_for("sites.webrings"))

    ring = WebRing.query.filter_by(slug=ring_slug).first_or_404()
    existing = WebRingMember.query.filter_by(
        ring_id=ring.id, site_id=current_user.site.id
    ).first()
    if existing:
        flash("You're already in this ring.", "warning")
        return redirect(url_for("sites.webrings"))

    position = ring.member_count
    member   = WebRingMember(ring_id=ring.id, site_id=current_user.site.id, position=position)
    db.session.add(member)
    db.session.commit()
    flash(f"Joined '{ring.name}'!", "success")
    return redirect(url_for("sites.webrings"))
