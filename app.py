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

class WeeklyMenu(db.Model):
    __tablename__ = "weekly_menus"
    id = db.Column(db.Integer, primary_key=True)
    mess_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), unique=True, nullable=False)
    menu_data = db.Column(db.Text, nullable=False)

# -------------------------
# SYSTEM INITIALIZATION
# -------------------------
def clean_and_init_db():
    # Only run this once to clean the system for the multi-org architecture
    # db.drop_all() # We will do this via a separate script to be safe
    db.create_all()

    # Seed Vanshmalhotra user
    user = User.query.filter_by(email="vanshmalhotra4321@gmail.com").first()
    if not user:
        user = User(
            email="vanshmalhotra4321@gmail.com",
            password=generate_password_hash("1111"),
            role="admin"
        )
        db.session.add(user)
        db.session.commit()
        
        # Add a default profile
        profile = MessProfile(
            user_id=user.id,
            admin_name="Vansh Malhotra",
            org_name="Bennett University Mess",
            org_type="University",
            capacity=1500,
            contact_phone="9999999999",
            location="Greater Noida"
        )
        db.session.add(profile)
        db.session.commit()

    # Ensure this user has the default menu
    menu = WeeklyMenu.query.filter_by(mess_id=user.id).first()
    if not menu:
        import json
        default_menu = {
            "Friday": {
                "Breakfast": ["Indori Poha - (130 Kcal)", "Green Chutney-(90Kcal)", "egg bhurji (185Kcal)", "Mix Fruits - (57 Kcal)", "masala Sprouts- (45 Kcal)", "Jam- (276 Kcal), Brown- (282 Kcal) & White Bread- (302 Kcal)", "Milk- (59 Kcal)/Tea- (30 Kcal)/Coffee- (30 Kcal)"],
                "Lunch": ["Paneer Lababdar- (185 Kcal)", "Khata Mitha Sitafal- (135Kcal)", "Red Masoor- (278 Kcal)", "Jeera Rice- (184 Kcal)", "Sambar- (133 Kcal)", "Roti- (280 Kcal)", "Carrot Beetroot-(80 Kcal)", "Curd- (78 Kcal)"],
                "Snack": ["Aloo papdi chaat", "Sweet-(120 Kcal) & Green Chutney(90Kcal)", "Tea- (30 Kcal)", "Tang- (54 Kcal)"],
                "Dinner": ["Aloo Capsicum -(80 Kcal)", "baingan bharta- (188 Kcal)", "Hariyali Dal-(149 Kcal)", "Steamed Rice- (130 Kcal)", "Roti- (280 Kcal)", "fruit custard", "Shirka Onion- (68 Kcal)", "Veg Clear Soup- (39 Kcal)"]
            },
            "Monday": {
                "Breakfast": ["Aloo Paratha - (180 Kcal)", "Curd - (98 Kcal)", "Mix Pickle - (25 Kcal)", "Sweet Corn - (120 Kcal)", "Bread & Butter - (210 Kcal)", "Tea/Coffee - (30 Kcal)"],
                "Lunch": ["Rajma Masala - (240 Kcal)", "Jeera Rice - (180 Kcal)", "Aloo Gobhi - (140 Kcal)", "Roti - (280 Kcal)", "Green Salad - (45 Kcal)", "Boondi Raita - (110 Kcal)"],
                "Snack": ["Samosa (1 pc) - (260 Kcal)", "Imli Chutney - (45 Kcal)", "Tea - (30 Kcal)", "Biscuits - (80 Kcal)"],
                "Dinner": ["Mix Veg - (160 Kcal)", "Dal Tadka - (185 Kcal)", "Rice - (130 Kcal)", "Roti - (280 Kcal)", "Gulab Jamun - (140 Kcal)"]
            },
            "Tuesday": {
                "Breakfast": ["Idli (2 pcs) - (120 Kcal)", "Sambar - (140 Kcal)", "Coconut Chutney - (80 Kcal)", "Vada - (150 Kcal)", "Fruits - (60 Kcal)", "Tea/Coffee - (30 Kcal)"],
                "Lunch": ["Kadi Pakoda - (210 Kcal)", "Steamed Rice - (130 Kcal)", "Bhindi Masala - (110 Kcal)", "Roti - (280 Kcal)", "Papad - (45 Kcal)"],
                "Snack": ["Red Sauce Pasta - (220 Kcal)", "Cold Coffee - (140 Kcal)"],
                "Dinner": ["Egg Curry - (210 Kcal)", "Aloo Matar - (140 Kcal)", "Rice - (130 Kcal)", "Roti - (280 Kcal)", "Sewaiyan - (180 Kcal)"]
            },
            "Wednesday": {
                "Breakfast": ["Puri Bhaji - (320 Kcal)", "Sooji Halwa - (210 Kcal)", "Chana Masala - (160 Kcal)", "Pickle - (20 Kcal)", "Tea/Coffee - (30 Kcal)"],
                "Lunch": ["Chole Bhature - (450 Kcal)", "Sweet Lassi - (180 Kcal)", "Onion Salad - (30 Kcal)", "Fried Chilli - (10 Kcal)"],
                "Snack": ["Bread Pakoda - (240 Kcal)", "Tomato Ketchup - (20 Kcal)", "Tea - (30 Kcal)"],
                "Dinner": ["Veg Biryani - (290 Kcal)", "Mirchi Ka Salan - (140 Kcal)", "Mix Raita - (80 Kcal)", "Moong Dal Halwa - (250 Kcal)"]
            },
            "Thursday": {
                "Breakfast": ["Veg Upma - (160 Kcal)", "Coconut Chutney - (80 Kcal)", "Boiled Egg - (75 Kcal)", "Toast - (90 Kcal)", "Juice - (110 Kcal)"],
                "Lunch": ["Dal Makhani - (320 Kcal)", "Butter Naan - (210 Kcal)", "Paneer Tikka - (180 Kcal)", "Jeera Rice - (180 Kcal)", "Salad - (40 Kcal)"],
                "Snack": ["Veg Maggi - (210 Kcal)", "Frooti - (120 Kcal)"],
                "Dinner": ["Malai Kofta - (280 Kcal)", "Yellow Dal - (140 Kcal)", "Rice - (130 Kcal)", "Paratha - (180 Kcal)", "Ice Cream - (150 Kcal)"]
            },
            "Saturday": {
                "Breakfast": ["Poha Jalebi - (280 Kcal)", "Sev - (45 Kcal)", "Fruits - (60 Kcal)", "Tea/Coffee - (30 Kcal)"],
                "Lunch": ["Kashmiri Dum Aloo - (190 Kcal)", "Peas Pulao - (160 Kcal)", "Dal Fry - (150 Kcal)", "Roti - (280 Kcal)", "Salad - (40 Kcal)"],
                "Snack": ["Pav Bhaji - (320 Kcal)", "Lemonade - (90 Kcal)"],
                "Dinner": ["Paneer Butter Masala - (260 Kcal)", "Naan - (190 Kcal)", "Jeera Rice - (180 Kcal)", "Dal Makhani - (320 Kcal)", "Rasgulla - (150 Kcal)"]
            },
            "Sunday": {
                "Breakfast": ["Masala Dosa - (250 Kcal)", "Sambar - (140 Kcal)", "Coconut Chutney - (80 Kcal)", "Tea/Coffee - (30 Kcal)"],
                "Lunch": ["Veg Pulao - (210 Kcal)", "Paneer Kurma - (180 Kcal)", "Roti - (280 Kcal)", "Boondi Raita - (110 Kcal)", "Papad - (45 Kcal)"],
                "Snack": ["Bhel Puri - (180 Kcal)", "Tea - (30 Kcal)"],
                "Dinner": ["Palak Paneer - (220 Kcal)", "Dal Tadka - (185 Kcal)", "Rice - (130 Kcal)", "Roti - (280 Kcal)", "Kheer - (210 Kcal)"]
            }
        }
        menu = WeeklyMenu(
            mess_id=user.id,
            menu_data=json.dumps(default_menu)
        )
        db.session.add(menu)
        db.session.commit()


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
