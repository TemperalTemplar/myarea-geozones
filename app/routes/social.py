"""
GeoZones — Social layer
Follow sites, like sites, activity feed.
"""
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from app import db

social_bp = Blueprint("social", __name__)


@social_bp.route("/feed")
@login_required
def feed():
    """Activity feed — updates from sites you follow."""
    from app.models import SiteFollow, SiteUpdate, SiteLike
    from sqlalchemy import desc

    # Sites I follow
    followed_site_ids = [f.site_id for f in
                         SiteFollow.query.filter_by(user_id=current_user.id).all()]

    updates = []
    if followed_site_ids:
        updates = SiteUpdate.query.filter(
            SiteUpdate.site_id.in_(followed_site_ids)
        ).order_by(desc(SiteUpdate.created_at)).limit(50).all()

    # Suggested sites to follow (most liked, not already followed)
    from app.models import Site
    suggested = Site.query.filter(
        Site.status == "approved",
        ~Site.id.in_(followed_site_ids + ([current_user.site.id] if current_user.site else []))
    ).order_by(desc(Site.hit_count)).limit(6).all()

    return render_template("social/feed.html",
                           updates=updates,
                           suggested=suggested,
                           followed_site_ids=followed_site_ids)


@social_bp.route("/follow/<int:site_id>", methods=["POST"])
@login_required
def follow(site_id):
    from app.models import Site, SiteFollow, SiteUpdate
    site = Site.query.get_or_404(site_id)

    if site.user_id == current_user.id:
        flash("You can't follow your own site.", "warning")
        return redirect(request.referrer or url_for("social.feed"))

    existing = SiteFollow.query.filter_by(
        user_id=current_user.id, site_id=site_id
    ).first()

    if existing:
        # Unfollow
        db.session.delete(existing)
        db.session.commit()
        flash(f"Unfollowed {site.title}.", "info")
    else:
        # Follow
        follow = SiteFollow(user_id=current_user.id, site_id=site_id)
        db.session.add(follow)
        # Post update to site owner's feed
        update = SiteUpdate(
            site_id=site_id,
            message=f"{current_user.username} started following your site!"
        )
        db.session.add(update)
        db.session.commit()
        flash(f"Now following {site.title}!", "success")

    return redirect(request.referrer or url_for("social.feed"))


@social_bp.route("/like/<int:site_id>", methods=["POST"])
@login_required
def like(site_id):
    from app.models import Site, SiteLike
    site = Site.query.get_or_404(site_id)

    existing = SiteLike.query.filter_by(
        user_id=current_user.id, site_id=site_id
    ).first()

    if existing:
        db.session.delete(existing)
        db.session.commit()
        return jsonify({"liked": False, "count": SiteLike.query.filter_by(site_id=site_id).count()})
    else:
        like = SiteLike(user_id=current_user.id, site_id=site_id)
        db.session.add(like)
        db.session.commit()
        return jsonify({"liked": True, "count": SiteLike.query.filter_by(site_id=site_id).count()})


@social_bp.route("/followers/<site_name>")
def followers(site_name):
    from app.models import Site, SiteFollow
    from sqlalchemy import desc
    site = Site.query.filter_by(name=site_name).first_or_404()
    follows = SiteFollow.query.filter_by(site_id=site.id).order_by(
        desc(SiteFollow.created_at)
    ).all()
    return render_template("social/followers.html", site=site, follows=follows)


@social_bp.route("/following")
@login_required
def following():
    from app.models import SiteFollow
    from sqlalchemy import desc
    follows = SiteFollow.query.filter_by(user_id=current_user.id).order_by(
        desc(SiteFollow.created_at)
    ).all()
    return render_template("social/following.html", follows=follows)
