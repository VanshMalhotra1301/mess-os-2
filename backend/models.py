from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text
from sqlalchemy.sql import func
try:
    from backend.database import Base
except ImportError:
    from database import Base


# -------------------------
# USER & PROFILES
# -------------------------
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(120), unique=True, index=True)
    password = Column(String(255))
    role = Column(String(20))

class MessProfile(Base):
    __tablename__ = "mess_profiles"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    admin_name = Column(String(100))
    org_name = Column(String(150))
    org_type = Column(String(50))
    capacity = Column(Integer)
    contact_phone = Column(String(20))
    location = Column(String(100))

class NGOProfile(Base):
    __tablename__ = "ngo_profiles"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    ngo_name = Column(String(150))
    contact_phone = Column(String(20))
    location = Column(String(100))
    service_radius = Column(Float)
    description = Column(Text)

class WeeklyMenu(Base):
    __tablename__ = "weekly_menus"
    id = Column(Integer, primary_key=True, index=True)
    mess_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    menu_data = Column(Text)

# -------------------------
# DATA MODELS
# -------------------------
class AttendanceRecord(Base):
    __tablename__ = "attendance_records"

    id = Column(Integer, primary_key=True, index=True)
    mess_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    date = Column(String(20))
    day_of_week = Column(String(15))
    meal_type = Column(String(20))
    expected_students = Column(Integer)
    actual_attendance = Column(Integer, default=0)
    prepared_qty = Column(Float, default=0.0)
    wasted_qty = Column(Float, default=0.0)

class SurplusPost(Base):
    __tablename__ = "surplus_posts"

    id = Column(Integer, primary_key=True, index=True)
    mess_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))  # Who posted it

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    meal_description = Column(String(200))
    quantity_kg = Column(Float)
    expiry_time = Column(String(20))
    status = Column(String(20), default="AVAILABLE")

class SurplusRecipient(Base):
    """Many-to-many: one broadcast can target multiple NGOs."""
    __tablename__ = "surplus_recipients"

    id = Column(Integer, primary_key=True, index=True)
    surplus_id = Column(Integer, ForeignKey("surplus_posts.id", ondelete="CASCADE"))
    ngo_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    status = Column(String(20), default="PENDING")  # PENDING / ACCEPTED / DECLINED

class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    mess_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    ngo_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))

    sender_type = Column(String(20))  # "Admin" or "NGO"
    message = Column(String(500))
    created_at = Column(DateTime(timezone=True), server_default=func.now())