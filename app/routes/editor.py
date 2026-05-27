"""
GeoZones — In-browser HTML editor
"""
import os
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, abort
from flask_login import login_required, current_user
from app import db

editor_bp = Blueprint("editor", __name__)


@editor_bp.route("/")
@login_required
def index():
    if not current_user.site or current_user.site.status != "approved":
        abort(403)
    from app.models import SiteFile
    site  = current_user.site
    files = SiteFile.query.filter_by(site_id=site.id).order_by(SiteFile.filename).all()
    # Default to index.html
    current_file = request.args.get("file", "index.html")
    sf = SiteFile.query.filter_by(site_id=site.id, filename=current_file).first()
    content = ""
    if sf and os.path.exists(sf.path):
        with open(sf.path, "r", errors="replace") as f:
            content = f.read()
    elif current_file == "index.html":
        content = _default_index(site)
    return render_template("editor/index.html", site=site, files=files,
                           current_file=current_file, content=content)


@editor_bp.route("/save", methods=["POST"])
@login_required
def save():
    from app.models import SiteFile
    from flask import current_app
    import mimetypes

    if not current_user.site or current_user.site.status != "approved":
        return jsonify({"error": "Forbidden"}), 403

    site     = current_user.site
    filename = request.json.get("filename", "").strip()
    content  = request.json.get("content", "")

    if not filename:
        return jsonify({"error": "Filename required"}), 400

    # Safety checks
    filename = filename.replace("..", "").replace("/", "").replace("\\", "")
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext in current_app.config["BLOCKED_EXTENSIONS"]:
        return jsonify({"error": "File type not allowed"}), 400

    # Write file
    from app.routes.sites import _site_upload_dir
    upload_dir = _site_upload_dir(site)
    disk_path  = os.path.join(upload_dir, filename)

    old_size = 0
    existing = SiteFile.query.filter_by(site_id=site.id, filename=filename).first()
    if existing:
        old_size = existing.size_bytes

    encoded = content.encode("utf-8")
    new_size = len(encoded)

    # Check storage
    max_bytes = current_app.config["MAX_STORAGE_MB"] * 1024 * 1024
    if site.storage_used - old_size + new_size > max_bytes:
        return jsonify({"error": f"Storage limit reached ({current_app.config['MAX_STORAGE_MB']}MB)"}), 400

    with open(disk_path, "w", encoding="utf-8") as f:
        f.write(content)

    mime = mimetypes.guess_type(filename)[0] or "text/plain"

    if existing:
        site.storage_used = site.storage_used - old_size + new_size
        existing.size_bytes = new_size
        existing.path = disk_path
    else:
        sf = SiteFile(
            site_id=site.id, filename=filename,
            path=disk_path, mime_type=mime,
            size_bytes=new_size,
            is_index=(filename.lower() == "index.html"),
        )
        db.session.add(sf)
        site.storage_used += new_size

    db.session.commit()

    # Post activity update so followers see the change
    if filename == "index.html":
        from app.models import SiteUpdate
        update = SiteUpdate(
            site_id=site.id,
            message=f"Updated their site!"
        )
        db.session.add(update)
        db.session.commit()

    return jsonify({"status": "saved", "size": new_size})


@editor_bp.route("/new-file", methods=["POST"])
@login_required
def new_file():
    from app.models import SiteFile
    from flask import current_app
    if not current_user.site or current_user.site.status != "approved":
        abort(403)

    site     = current_user.site
    filename = request.form.get("filename", "").strip()
    filename = filename.replace("..", "").replace("/", "").replace("\\", "")

    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext in current_app.config["BLOCKED_EXTENSIONS"]:
        flash("File type not allowed.", "danger")
        return redirect(url_for("editor.index"))

    existing = SiteFile.query.filter_by(site_id=site.id, filename=filename).first()
    if existing:
        return redirect(url_for("editor.index", file=filename))

    from app.routes.sites import _site_upload_dir
    upload_dir = _site_upload_dir(site)
    disk_path  = os.path.join(upload_dir, filename)

    # Create empty file
    with open(disk_path, "w") as f:
        if filename.endswith(".html") or filename.endswith(".htm"):
            f.write(_default_page(site, filename))
        else:
            f.write("")

    import mimetypes
    mime = mimetypes.guess_type(filename)[0] or "text/plain"
    sf = SiteFile(site_id=site.id, filename=filename, path=disk_path,
                  mime_type=mime, size_bytes=0,
                  is_index=(filename.lower() == "index.html"))
    db.session.add(sf)
    db.session.commit()
    return redirect(url_for("editor.index", file=filename))


def _default_index(site):
    return f"""<!DOCTYPE html>
<html>
<head>
<title>Welcome to {site.title}!</title>
<style>
body {{ background-color: {site.bg_color}; color: {site.text_color}; font-family: Arial, sans-serif; }}
a {{ color: {site.link_color}; }}
h1 {{ text-align: center; }}
.center {{ text-align: center; }}
</style>
</head>
<body>
<h1>Welcome to {site.title}!</h1>
<div class="center">
  <p>This page is under construction!</p>
  <img src="https://web.archive.org/web/20090830010030/http://www.geocities.com/SiliconValley/Way/3774/const.gif" alt="Under Construction">
  <p><em>Last updated: {site.created_at.strftime('%B %d, %Y')}</em></p>
  <hr>
  <p>You are visitor number <b>{{{{ site.hit_count }}}}</b></p>
</div>
</body>
</html>"""


def _default_page(site, filename):
    return f"""<!DOCTYPE html>
<html>
<head>
<title>{filename} - {site.title}</title>
<style>
body {{ background-color: {site.bg_color}; color: {site.text_color}; font-family: Arial, sans-serif; }}
a {{ color: {site.link_color}; }}
</style>
</head>
<body>
<h1>{filename}</h1>
<p>Edit this page in the GeoZones editor.</p>
<p><a href="index.html">Back to home</a></p>
</body>
</html>"""
