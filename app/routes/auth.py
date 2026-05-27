from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from app import db

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))
    if request.method == "POST":
        from app.models import User
        identifier = request.form.get("identifier", "").strip()
        password   = request.form.get("password", "")
        user = User.query.filter_by(username=identifier).first() or \
               User.query.filter_by(email=identifier).first()
        if user and user.check_password(password):
            if user.is_banned:
                flash("Your account has been suspended.", "danger")
                return redirect(url_for("auth.login"))
            from datetime import datetime, timezone
            user.last_login = datetime.now(timezone.utc)
            db.session.commit()
            login_user(user, remember=bool(request.form.get("remember")))
            return redirect(request.args.get("next") or url_for("main.index"))
        flash("Invalid username or password.", "danger")
    return render_template("auth/login.html")


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))
    if request.method == "POST":
        from app.models import User
        username = request.form.get("username", "").strip()
        email    = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        password2= request.form.get("password2", "")
        errors = []
        if len(username) < 3: errors.append("Username too short.")
        if len(password) < 8: errors.append("Password must be 8+ characters.")
        if password != password2: errors.append("Passwords don't match.")
        if User.query.filter_by(username=username).first(): errors.append("Username taken.")
        if User.query.filter_by(email=email).first(): errors.append("Email already registered.")
        if errors:
            for e in errors: flash(e, "danger")
            return render_template("auth/register.html", username=username, email=email)
        user = User(username=username, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        login_user(user)
        flash("Welcome to GeoZones! Apply for your site below.", "success")
        return redirect(url_for("sites.apply"))
    return render_template("auth/register.html")


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("main.index"))


@auth_bp.route("/oidc/login")
def oidc_login():
    from flask import current_app
    from app import oauth
    if not current_app.config.get("OIDC_CLIENT_ID"):
        flash("SSO not configured.", "warning")
        return redirect(url_for("auth.login"))
    redirect_uri = current_app.config.get("OIDC_REDIRECT_URI") or \
                   url_for("auth.oidc_callback", _external=True)
    return oauth.authentik.authorize_redirect(redirect_uri)


@auth_bp.route("/oidc/callback")
def oidc_callback():
    from flask import current_app
    from app import oauth
    from app.models import User
    try:
        token    = oauth.authentik.authorize_access_token()
        userinfo = token.get("userinfo") or oauth.authentik.userinfo()
    except Exception:
        flash("SSO login failed.", "danger")
        return redirect(url_for("auth.login"))
    sub      = userinfo["sub"]
    email    = userinfo.get("email", "")
    username = userinfo.get("preferred_username", sub[:32])
    user = User.query.filter_by(oidc_sub=sub).first()
    if not user:
        user = User.query.filter_by(email=email).first()
        if user:
            user.oidc_sub = sub
        else:
            base = username[:28].replace(" ", "_")
            candidate = base; n = 1
            while User.query.filter_by(username=candidate).first():
                candidate = f"{base}{n}"; n += 1
            user = User(username=candidate, email=email, oidc_sub=sub)
            db.session.add(user)
    from datetime import datetime, timezone
    user.last_login = datetime.now(timezone.utc)
    db.session.commit()
    if user.is_banned:
        flash("Your account has been suspended.", "danger")
        return redirect(url_for("auth.login"))
    login_user(user, remember=True)
    return redirect(url_for("main.index"))
