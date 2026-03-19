from flask import Flask, render_template, request, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import os
import urllib.parse
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(
    __name__,
    template_folder="frontend",
    static_folder="frontend/static",
    static_url_path="/static"
)

# Secret key for sessions
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "supersecretkey")

# Backend URL for Frontend Communication
BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8000")

# -------------------------
# DATABASE CONFIG (Supabase PostgreSQL)
# -------------------------
SUPABASE_PASSWORD_RAW = os.getenv("SUPABASE_PASSWORD", "Vansh@ww22iixxzz")
SUPABASE_PASSWORD = urllib.parse.quote_plus(SUPABASE_PASSWORD_RAW)

app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv(
    "DATABASE_URL", 
    f"postgresql://postgres.zipaybqpbzdtpuwlufbp:{SUPABASE_PASSWORD}@aws-1-ap-northeast-1.pooler.supabase.com:6543/postgres"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)


# -------------------------
# USER MODELS
# -------------------------
class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # admin or ngo

class MessProfile(db.Model):
    __tablename__ = "mess_profiles"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    admin_name = db.Column(db.String(100))
    org_name = db.Column(db.String(150))
    org_type = db.Column(db.String(50))
    capacity = db.Column(db.Integer)
    contact_phone = db.Column(db.String(20))
    location = db.Column(db.String(100))

class NGOProfile(db.Model):
    __tablename__ = "ngo_profiles"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    ngo_name = db.Column(db.String(150))
    contact_phone = db.Column(db.String(20))
    location = db.Column(db.String(100))
    service_radius = db.Column(db.Float)
    description = db.Column(db.Text)

# -------------------------
# SYSTEM INITIALIZATION
# -------------------------
def clean_and_init_db():
    # Only run this once to clean the system for the multi-org architecture
    # db.drop_all() # We will do this via a separate script to be safe
    db.create_all()


# -------------------------
# ROUTES
# -------------------------

@app.context_processor
def inject_globals():
    return dict(BACKEND_URL=BACKEND_URL)

@app.route("/")
def home():
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        user = User.query.filter_by(email=email).first()

        if user and check_password_hash(user.password, password):
            session["user_id"] = user.id
            session["email"] = user.email
            session["role"] = user.role

            if user.role == "admin":
                profile = MessProfile.query.filter_by(user_id=user.id).first()
                if profile:
                    session["org_name"] = profile.org_name
                    session["capacity"] = profile.capacity
                return redirect(url_for("admin_dashboard"))
            else:
                profile = NGOProfile.query.filter_by(user_id=user.id).first()
                if profile:
                    session["ngo_name"] = profile.ngo_name
                return redirect(url_for("ngo_dashboard"))
        else:
            return redirect(url_for("login", error="invalid"))

    return render_template("login.html")


@app.route("/register_mess", methods=["POST"])
def register_mess():
    email = request.form["email"]
    password = request.form["password"]
    
    if User.query.filter_by(email=email).first():
        return redirect(url_for("login", error="exists"))
        
    user = User(
        email=email,
        password=generate_password_hash(password),
        role="admin"
    )
    db.session.add(user)
    db.session.commit()
    
    profile = MessProfile(
        user_id=user.id,
        admin_name=request.form["admin_name"],
        org_name=request.form["org_name"],
        org_type=request.form["org_type"],
        capacity=int(request.form["capacity"]),
        contact_phone=request.form["contact_phone"],
        location=request.form["location"]
    )
    db.session.add(profile)
    db.session.commit()
    
    return redirect(url_for("login", success="registered"))


@app.route("/register_ngo", methods=["POST"])
def register_ngo():
    email = request.form["email"]
    password = request.form["password"]
    
    if User.query.filter_by(email=email).first():
        return redirect(url_for("login", error="exists"))
        
    user = User(
        email=email,
        password=generate_password_hash(password),
        role="ngo"
    )
    db.session.add(user)
    db.session.commit()
    
    profile = NGOProfile(
        user_id=user.id,
        ngo_name=request.form["ngo_name"],
        contact_phone=request.form["contact_phone"],
        location=request.form["location"],
        service_radius=float(request.form["service_radius"]),
        description=request.form["description"]
    )
    db.session.add(profile)
    db.session.commit()
    
    return redirect(url_for("login", success="registered"))


@app.route("/admin")
def admin_dashboard():
    if session.get("role") != "admin":
        return redirect(url_for("login"))
    return render_template("admin_dashboard.html", user_id=session.get("user_id"), org_name=session.get("org_name", "Mess Organization"), capacity=session.get("capacity", 0))


@app.route("/ngo")
def ngo_dashboard():
    if session.get("role") != "ngo":
        return redirect(url_for("login"))
    return render_template("ngo_dashboard.html", user_id=session.get("user_id"), ngo_name=session.get("ngo_name", "NGO Organization"))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# -------------------------
# APP START
# -------------------------
if __name__ == "__main__":
    with app.app_context():
        clean_and_init_db()
    app.run(debug=True)
