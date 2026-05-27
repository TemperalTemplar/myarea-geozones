"""
GeoZones — Admin Panel
"""
import functools
from flask import Blueprint, render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user
from app import db
from datetime import datetime, timezone

admin_bp = Blueprint("admin", __name__)


def admin_required(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            abort(403)
        return fn(*args, **kwargs)
    return wrapper


@admin_bp.route("/")
@login_required
@admin_required
def index():
    from app.models import User, Site, SiteApplication
    from sqlalchemy import desc
    stats = {
        "users":       User.query.count(),
        "sites":       Site.query.filter_by(status="approved").count(),
        "pending":     SiteApplication.query.filter_by(status="pending").count(),
        "total_sites": Site.query.count(),
    }
    pending = SiteApplication.query.filter_by(status="pending").order_by(
        desc(SiteApplication.created_at)
    ).all()
    return render_template("admin/index.html", stats=stats, pending=pending)


@admin_bp.route("/applications")
@login_required
@admin_required
def applications():
    from app.models import SiteApplication
    from sqlalchemy import desc
    status = request.args.get("status", "pending")
    apps   = SiteApplication.query.filter_by(status=status).order_by(
        desc(SiteApplication.created_at)
    ).all()
    return render_template("admin/applications.html", apps=apps, status=status)


@admin_bp.route("/applications/<int:app_id>/approve", methods=["POST"])
@login_required
@admin_required
def approve(app_id):
    from app.models import SiteApplication, Site
    application = SiteApplication.query.get_or_404(app_id)

    # Create the site
    site = Site(
        user_id=application.user_id,
        name=application.site_name,
        title=application.site_title,
        neighborhood=application.neighborhood,
        description=application.description,
        status="approved",
        approved_at=datetime.now(timezone.utc),
        approved_by=current_user.id,
    )
    db.session.add(site)

    application.status      = "approved"
    application.reviewed_by = current_user.id
    application.reviewed_at = datetime.now(timezone.utc)

    db.session.commit()

    # Create uploads directory
    import os
    from flask import current_app
    upload_dir = os.path.join(current_app.config["UPLOAD_FOLDER"], "geozones", str(site.id))
    os.makedirs(upload_dir, exist_ok=True)

    flash(f"Site '{site.name}' approved and created.", "success")
    return redirect(url_for("admin.applications"))


@admin_bp.route("/applications/<int:app_id>/reject", methods=["POST"])
@login_required
@admin_required
def reject(app_id):
    from app.models import SiteApplication
    application = SiteApplication.query.get_or_404(app_id)
    reason = request.form.get("reason", "").strip()

    application.status        = "rejected"
    application.reviewed_by   = current_user.id
    application.reviewed_at   = datetime.now(timezone.utc)
    application.reject_reason = reason

    db.session.commit()
    flash("Application rejected.", "info")
    return redirect(url_for("admin.applications"))


@admin_bp.route("/sites")
@login_required
@admin_required
def sites():
    from app.models import Site
    from sqlalchemy import desc
    page  = request.args.get("page", 1, type=int)
    status = request.args.get("status", "approved")
    pagination = Site.query.filter_by(status=status).order_by(
        desc(Site.created_at)
    ).paginate(page=page, per_page=30, error_out=False)
    return render_template("admin/sites.html", pagination=pagination, status=status)


@admin_bp.route("/sites/<int:site_id>/suspend", methods=["POST"])
@login_required
@admin_required
def suspend_site(site_id):
    from app.models import Site
    site = Site.query.get_or_404(site_id)
    site.status = "suspended" if site.status == "approved" else "approved"
    db.session.commit()
    flash(f"Site '{site.name}' {'suspended' if site.status == 'suspended' else 'reinstated'}.", "success")
    return redirect(url_for("admin.sites"))


@admin_bp.route("/users")
@login_required
@admin_required
def users():
    from app.models import User
    from sqlalchemy import desc
    page       = request.args.get("page", 1, type=int)
    pagination = User.query.order_by(desc(User.created_at)).paginate(
        page=page, per_page=30, error_out=False
    )
    return render_template("admin/users.html", pagination=pagination)


@admin_bp.route("/users/<int:user_id>/ban", methods=["POST"])
@login_required
@admin_required
def ban_user(user_id):
    from app.models import User
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash("Can't ban yourself.", "danger")
        return redirect(url_for("admin.users"))
    user.is_banned = not user.is_banned
    db.session.commit()
    flash(f"{'Banned' if user.is_banned else 'Unbanned'} {user.username}.", "success")
    return redirect(url_for("admin.users"))
