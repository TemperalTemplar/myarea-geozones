"""
GeoZones — Database Models
"""
from __future__ import annotations
from datetime import datetime, timezone
from flask_login import UserMixin
from app import db


def now_utc():
    return datetime.now(timezone.utc)


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id            = db.Column(db.Integer, primary_key=True)
    username      = db.Column(db.String(32), unique=True, nullable=False, index=True)
    email         = db.Column(db.String(254), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=True)
    oidc_sub      = db.Column(db.String(256), unique=True, nullable=True)
    is_admin      = db.Column(db.Boolean, default=False)
    is_banned     = db.Column(db.Boolean, default=False)
    created_at    = db.Column(db.DateTime(timezone=True), default=now_utc)
    last_login    = db.Column(db.DateTime(timezone=True), nullable=True)

    site = db.relationship("Site", back_populates="owner", uselist=False, foreign_keys="[Site.user_id]",
                           cascade="all, delete-orphan")

    def set_password(self, password):
        from werkzeug.security import generate_password_hash
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        from werkzeug.security import check_password_hash
        return self.password_hash and check_password_hash(self.password_hash, password)


class Site(db.Model):
    """A user's GeoZones personal site."""
    __tablename__ = "sites"

    id            = db.Column(db.Integer, primary_key=True)
    user_id       = db.Column(db.Integer, db.ForeignKey("users.id"), unique=True, nullable=False)
    name          = db.Column(db.String(64), unique=True, nullable=False, index=True)
    title         = db.Column(db.String(128), nullable=False)
    description   = db.Column(db.Text, nullable=True)
    neighborhood  = db.Column(db.String(32), nullable=False)

    # Status
    status        = db.Column(db.String(16), default="pending")  # pending|approved|rejected|suspended
    approved_at   = db.Column(db.DateTime(timezone=True), nullable=True)
    approved_by   = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    reject_reason = db.Column(db.Text, nullable=True)

    # Stats
    hit_count     = db.Column(db.Integer, default=0)
    storage_used  = db.Column(db.BigInteger, default=0)  # bytes

    # Settings
    under_construction = db.Column(db.Boolean, default=False)
    bg_color      = db.Column(db.String(16), default="#000080")
    text_color    = db.Column(db.String(16), default="#ffffff")
    link_color    = db.Column(db.String(16), default="#ffff00")

    created_at    = db.Column(db.DateTime(timezone=True), default=now_utc)
    updated_at    = db.Column(db.DateTime(timezone=True), default=now_utc, onupdate=now_utc)

    owner         = db.relationship("User", back_populates="site", foreign_keys=[user_id])
    files         = db.relationship("SiteFile", back_populates="site", cascade="all, delete-orphan")
    guestbook     = db.relationship("GuestbookEntry", back_populates="site", cascade="all, delete-orphan")
    webring_memberships = db.relationship("WebRingMember", back_populates="site", cascade="all, delete-orphan")

    @property
    def url_path(self):
        return f"/{self.neighborhood}/{self.name}/"

    @property
    def storage_mb(self):
        return round(self.storage_used / (1024 * 1024), 2)

    @property
    def storage_pct(self):
        from flask import current_app
        max_bytes = current_app.config["MAX_STORAGE_MB"] * 1024 * 1024
        return min(100, int(self.storage_used / max_bytes * 100))

    @property
    def is_live(self):
        return self.status == "approved"


class SiteFile(db.Model):
    """A file belonging to a site."""
    __tablename__ = "site_files"

    id          = db.Column(db.Integer, primary_key=True)
    site_id     = db.Column(db.Integer, db.ForeignKey("sites.id"), nullable=False, index=True)
    filename    = db.Column(db.String(256), nullable=False)
    path        = db.Column(db.String(512), nullable=False)  # disk path
    mime_type   = db.Column(db.String(128), nullable=True)
    size_bytes  = db.Column(db.Integer, default=0)
    is_index    = db.Column(db.Boolean, default=False)  # is this index.html?
    created_at  = db.Column(db.DateTime(timezone=True), default=now_utc)
    updated_at  = db.Column(db.DateTime(timezone=True), default=now_utc, onupdate=now_utc)

    site        = db.relationship("Site", back_populates="files")

    __table_args__ = (
        db.UniqueConstraint("site_id", "filename", name="uq_site_file"),
    )


class GuestbookEntry(db.Model):
    """A signed guestbook entry."""
    __tablename__ = "guestbook_entries"

    id          = db.Column(db.Integer, primary_key=True)
    site_id     = db.Column(db.Integer, db.ForeignKey("sites.id"), nullable=False, index=True)
    author_name = db.Column(db.String(64), nullable=False)
    author_url  = db.Column(db.String(256), nullable=True)
    message     = db.Column(db.Text, nullable=False)
    is_approved = db.Column(db.Boolean, default=True)  # site owner can delete
    created_at  = db.Column(db.DateTime(timezone=True), default=now_utc, index=True)

    site        = db.relationship("Site", back_populates="guestbook")


class WebRing(db.Model):
    """A web ring — a circular chain of related sites."""
    __tablename__ = "webrings"

    id          = db.Column(db.Integer, primary_key=True)
    name        = db.Column(db.String(128), unique=True, nullable=False)
    slug        = db.Column(db.String(128), unique=True, nullable=False, index=True)
    description = db.Column(db.Text, nullable=True)
    neighborhood= db.Column(db.String(32), nullable=True)
    owner_id    = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at  = db.Column(db.DateTime(timezone=True), default=now_utc)

    owner       = db.relationship("User", foreign_keys=[owner_id])
    members     = db.relationship("WebRingMember", back_populates="ring",
                                  cascade="all, delete-orphan",
                                  order_by="WebRingMember.position")

    @property
    def member_count(self):
        return len(self.members)


class WebRingMember(db.Model):
    """A site's membership in a web ring."""
    __tablename__ = "webring_members"

    id          = db.Column(db.Integer, primary_key=True)
    ring_id     = db.Column(db.Integer, db.ForeignKey("webrings.id"), nullable=False, index=True)
    site_id     = db.Column(db.Integer, db.ForeignKey("sites.id"), nullable=False)
    position    = db.Column(db.Integer, nullable=False)
    joined_at   = db.Column(db.DateTime(timezone=True), default=now_utc)

    ring        = db.relationship("WebRing", back_populates="members")
    site        = db.relationship("Site", back_populates="webring_memberships")

    __table_args__ = (
        db.UniqueConstraint("ring_id", "site_id", name="uq_ring_site"),
    )


class SiteApplication(db.Model):
    """A user's application for a GeoZones site."""
    __tablename__ = "site_applications"

    id           = db.Column(db.Integer, primary_key=True)
    user_id      = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    site_name    = db.Column(db.String(64), nullable=False)
    site_title   = db.Column(db.String(128), nullable=False)
    neighborhood = db.Column(db.String(32), nullable=False)
    description  = db.Column(db.Text, nullable=True)
    reason       = db.Column(db.Text, nullable=True)  # why they want a site
    status       = db.Column(db.String(16), default="pending")
    reviewed_by  = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    reviewed_at  = db.Column(db.DateTime(timezone=True), nullable=True)
    reject_reason= db.Column(db.Text, nullable=True)
    created_at   = db.Column(db.DateTime(timezone=True), default=now_utc, index=True)

    user         = db.relationship("User", foreign_keys=[user_id])
    reviewer     = db.relationship("User", foreign_keys=[reviewed_by])


class SiteFollow(db.Model):
    """A user following a site."""
    __tablename__ = "site_follows"

    id          = db.Column(db.Integer, primary_key=True)
    user_id     = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    site_id     = db.Column(db.Integer, db.ForeignKey("sites.id"), nullable=False, index=True)
    created_at  = db.Column(db.DateTime(timezone=True), default=now_utc, index=True)

    user        = db.relationship("User", foreign_keys=[user_id])
    site        = db.relationship("Site", foreign_keys=[site_id])

    __table_args__ = (
        db.UniqueConstraint("user_id", "site_id", name="uq_follow"),
    )


class SiteUpdate(db.Model):
    """An activity update posted when a site's files change."""
    __tablename__ = "site_updates"

    id          = db.Column(db.Integer, primary_key=True)
    site_id     = db.Column(db.Integer, db.ForeignKey("sites.id"), nullable=False, index=True)
    message     = db.Column(db.String(256), nullable=False)
    created_at  = db.Column(db.DateTime(timezone=True), default=now_utc, index=True)

    site        = db.relationship("Site")


class SiteLike(db.Model):
    """A user liking a site."""
    __tablename__ = "site_likes"

    id          = db.Column(db.Integer, primary_key=True)
    user_id     = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    site_id     = db.Column(db.Integer, db.ForeignKey("sites.id"), nullable=False, index=True)
    created_at  = db.Column(db.DateTime(timezone=True), default=now_utc)

    user        = db.relationship("User", foreign_keys=[user_id])
    site        = db.relationship("Site", foreign_keys=[site_id])

    __table_args__ = (
        db.UniqueConstraint("user_id", "site_id", name="uq_like"),
    )
