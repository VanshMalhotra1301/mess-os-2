from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel
from datetime import datetime
import pandas as pd
from typing import List
import io
import csv
from fastapi.responses import StreamingResponse

# --- IMPORTS ---
from database import get_db, engine
from models import Base, SurplusPost, SurplusRecipient, AttendanceRecord, ChatMessage, WeeklyMenu
from websocket_manager import manager
from ai_engine.predictor import predictor 

# --- INIT DATABASE ---
# This line ensures tables are created if they don't exist yet
Base.metadata.create_all(bind=engine)

# Initialize App
app = FastAPI(title="SmartMess AI Backend")

# Allow Frontend to talk to Backend (CORS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- PYDANTIC MODELS (Data Validation) ---
from typing import Optional, List, Dict, Any

class MenuRequest(BaseModel):
    mess_id: int
    menu_data: Dict[str, Any]

class PredictionRequest(BaseModel):
    mess_id: int
    date: str
    meal_type: str
    expected_students: int

class LogRequest(BaseModel):
    mess_id: int
    date: str
    meal_type: str
    expected_students: int
    actual_attendance: int = 0 

class SurplusAlert(BaseModel):
    mess_id: int
    ngo_ids: Optional[List[int]] = []  # Empty list = broadcast to all
    meal_description: str
    quantity_kg: float
    expiry_time: str 

class ItemAnalysisRequest(BaseModel):
    mess_id: int
    date: str
    meal_type: str
    expected_students: int

class ChatRequest(BaseModel):
    mess_id: int
    ngo_id: int
    sender_type: str
    message: str

# --- API ROUTES ---

@app.get("/")
def home():
    return {"message": "SmartMess AI Server is Running 🚀"}

# 1. AI Prediction Endpoint (Overall)
@app.post("/api/predict")
def predict_demand(request: PredictionRequest):
    """
    AI Endpoint: Returns predicted attendance using the trained model.
    """
    prediction = predictor.predict_attendance(
        request.date, request.meal_type, request.expected_students
    )
    return {
        "predicted_attendance": prediction,
        "suggested_prep_kg": prediction * 0.25 # Assuming 250g per person
    }

# --- NEW ENDPOINT: Food Item Analysis ---
@app.post("/api/predict-item-analysis")
def predict_item_analysis_endpoint(req: ItemAnalysisRequest):
    """
    Returns detailed item-level breakdown of the prediction
    and status (Low/Balanced/High) for specific food items.
    """
    result = predictor.predict_item_analysis(req.date, req.meal_type, req.expected_students)
    return result

# --- NEW ENDPOINT: Model Insights ---
@app.get("/api/model-insights")
def get_model_insights():
    """
    Returns feature importance data from the AI model
    to visualize what factors are driving predictions.
    """
    return predictor.get_model_insights()

# 2. Save Log Endpoint
@app.post("/api/save-log")
def save_log(request: LogRequest, db: Session = Depends(get_db)):
    # Auto-calculate day name
    day_name = pd.to_datetime(request.date).day_name()
    
    new_record = AttendanceRecord(
        mess_id=request.mess_id,
        date=request.date,
        day_of_week=day_name,
        meal_type=request.meal_type,
        expected_students=request.expected_students,
        actual_attendance=request.actual_attendance, 
        prepared_qty=0.0,
    )
    db.add(new_record)
    db.commit()
    return {"status": "Saved", "id": new_record.id}

# 3. Fetch Attendance Logs (For Attendance Page)
@app.get("/api/attendance-logs")
def get_logs(mess_id: int, db: Session = Depends(get_db)):
    logs = db.query(AttendanceRecord).filter(AttendanceRecord.mess_id == mess_id).order_by(AttendanceRecord.id.desc()).limit(50).all()
    return logs

# --- NEW ENDPOINTS: Menu Management ---
import json

@app.get("/api/menu/{mess_id}")
def get_menu(mess_id: int, db: Session = Depends(get_db)):
    menu = db.query(WeeklyMenu).filter(WeeklyMenu.mess_id == mess_id).first()
    if menu:
        return {"status": "success", "menu_data": json.loads(menu.menu_data)}
    else:
        raise HTTPException(status_code=404, detail="Menu not found")

@app.post("/api/menu")
def save_menu(req: MenuRequest, db: Session = Depends(get_db)):
    menu = db.query(WeeklyMenu).filter(WeeklyMenu.mess_id == req.mess_id).first()
    if menu:
        menu.menu_data = json.dumps(req.menu_data)
    else:
        new_menu = WeeklyMenu(mess_id=req.mess_id, menu_data=json.dumps(req.menu_data))
        db.add(new_menu)
    db.commit()
    return {"status": "success"}

# 4. Analytics Endpoint
@app.get("/api/analytics/waste-trend")
def get_waste_trend(mess_id: int, db: Session = Depends(get_db)):
    records = db.query(AttendanceRecord).filter(AttendanceRecord.mess_id == mess_id).order_by(AttendanceRecord.id.desc()).limit(7).all()
    records = records[::-1] 
    
    data = {
        "labels": [r.day_of_week[:3] for r in records],
        "waste": [round(r.wasted_qty, 1) if r.wasted_qty else 0 for r in records]
    }
    return data

# 4b. Menu-Aware Attendance Analytics Endpoint
@app.get("/api/analytics/menu-attendance")
def get_menu_attendance(mess_id: int, db: Session = Depends(get_db)):
    records = db.query(AttendanceRecord).filter(AttendanceRecord.mess_id == mess_id).order_by(AttendanceRecord.id.desc()).limit(30).all()
    records = records[::-1]
    return [
        {
            "id": r.id,
            "date": r.date,
            "day_of_week": r.day_of_week,
            "meal_type": r.meal_type,
            "predicted": r.expected_students,
            "actual": r.actual_attendance
        }
        for r in records
    ]

# 5. Broadcast Surplus Endpoint (Write Data)
@app.post("/api/broadcast-surplus")
async def broadcast_surplus(alert: SurplusAlert, db: Session = Depends(get_db)):
    new_post = SurplusPost(
        mess_id=alert.mess_id,
        meal_description=alert.meal_description,
        quantity_kg=alert.quantity_kg,
        expiry_time=alert.expiry_time,
        status="AVAILABLE"
    )
    db.add(new_post)
    db.commit()
    db.refresh(new_post)

    # Determine recipient NGOs
    from models import NGOProfile
    target_ngo_ids = alert.ngo_ids
    if not target_ngo_ids:
        # Broadcast to ALL registered NGOs
        all_ngos = db.query(NGOProfile).all()
        target_ngo_ids = [n.user_id for n in all_ngos]

    for ngo_id in target_ngo_ids:
        recipient = SurplusRecipient(
            surplus_id=new_post.id,
            ngo_id=ngo_id,
            status="PENDING"
        )
        db.add(recipient)
    db.commit()

    # Real-Time WebSocket Broadcast
    message = {
        "type": "NEW_SURPLUS",
        "data": {
            "id": new_post.id,
            "description": alert.meal_description,
            "quantity": alert.quantity_kg,
            "expiry": alert.expiry_time,
            "mess_id": alert.mess_id,
            "target_ngo_ids": target_ngo_ids
        }
    }
    await manager.broadcast(message)
    return {"status": "Broadcast Sent", "id": new_post.id, "recipients": len(target_ngo_ids)}

# 6. Fetch Broadcast History Endpoint (Admin view)
@app.get("/api/broadcast-history")
def get_broadcast_history(mess_id: int, db: Session = Depends(get_db)):
    from models import NGOProfile
    posts = db.query(SurplusPost).filter(SurplusPost.mess_id == mess_id).order_by(SurplusPost.id.desc()).limit(20).all()
    result = []
    for p in posts:
        recipients = db.query(SurplusRecipient).filter(SurplusRecipient.surplus_id == p.id).all()
        ngo_names = []
        for r in recipients:
            ngo = db.query(NGOProfile).filter(NGOProfile.user_id == r.ngo_id).first()
            if ngo:
                ngo_names.append(ngo.ngo_name)
        result.append({
            "id": p.id,
            "meal_description": p.meal_description,
            "quantity_kg": p.quantity_kg,
            "expiry_time": p.expiry_time,
            "status": p.status,
            "created_at": str(p.created_at),
            "ngo_names": ngo_names
        })
    return result

# 6b. NGO Donation History (filtered to this NGO only)
@app.get("/api/ngo/history")
def get_ngo_history(ngo_id: int, db: Session = Depends(get_db)):
    from models import MessProfile
    # Find all surplus posts where this NGO is a recipient
    recipient_rows = db.query(SurplusRecipient).filter(SurplusRecipient.ngo_id == ngo_id).all()
    surplus_ids = [r.surplus_id for r in recipient_rows]
    posts = db.query(SurplusPost).filter(SurplusPost.id.in_(surplus_ids)).order_by(SurplusPost.id.desc()).limit(50).all()
    result = []
    for p in posts:
        mess = db.query(MessProfile).filter(MessProfile.user_id == p.mess_id).first()
        result.append({
            "id": p.id,
            "meal_description": p.meal_description,
            "quantity_kg": p.quantity_kg,
            "expiry_time": p.expiry_time,
            "status": p.status,
            "created_at": str(p.created_at),
            "org_name": mess.org_name if mess else "Unknown Mess"
        })
    return result

# 6c. Pending Broadcasts (For NGO Feed on Load)
@app.get("/api/ngo/pending-broadcasts")
def get_pending_broadcasts(ngo_id: int, db: Session = Depends(get_db)):
    from models import MessProfile
    recipient_rows = db.query(SurplusRecipient).filter(
        SurplusRecipient.ngo_id == ngo_id,
        SurplusRecipient.status == "PENDING"
    ).all()
    surplus_ids = [r.surplus_id for r in recipient_rows]
    posts = db.query(SurplusPost).filter(
        SurplusPost.id.in_(surplus_ids),
        SurplusPost.status == "AVAILABLE"
    ).order_by(SurplusPost.id.desc()).all()
    
    result = []
    for p in posts:
        mess = db.query(MessProfile).filter(MessProfile.user_id == p.mess_id).first()
        result.append({
            "id": p.id,
            "description": p.meal_description,
            "quantity": p.quantity_kg,
            "expiry": p.expiry_time,
            "mess_id": p.mess_id,
            "mess": mess.org_name if mess else "Hostel Mess"
        })
    return result

@app.get("/api/ngo/analytics")
def get_analytics(ngo_id: int, db: Session = Depends(get_db)):
    """
    Returns real data for the Impact Charts - filtered to this NGO's received donations.
    """
    recipient_rows = db.query(SurplusRecipient).filter(SurplusRecipient.ngo_id == ngo_id).all()
    surplus_ids = [r.surplus_id for r in recipient_rows]
    posts = db.query(SurplusPost).filter(SurplusPost.id.in_(surplus_ids)).all() if surplus_ids else []

    total_kg = sum(p.quantity_kg for p in posts)
    days_map = {"Mon": 0, "Tue": 0, "Wed": 0, "Thu": 0, "Fri": 0, "Sat": 0, "Sun": 0}
    for post in posts:
        if post.created_at:
            day_name = post.created_at.strftime("%a")
            if day_name in days_map:
                days_map[day_name] += post.quantity_kg

    return {
        "total_kg": round(total_kg, 1),
        "chart_labels": list(days_map.keys()),
        "chart_data": list(days_map.values())
    }

# --- NEW ENDPOINT: Sustainability & Carbon Footprint Dashboard ---
@app.get("/api/sustainability-metrics")
def get_sustainability_metrics(mess_id: int, db: Session = Depends(get_db)):
    """
    Returns data for the Carbon Footprint & Sustainability Dashboard.
    Includes: waste avoided, CO2 equivalent, meals donated, ESG score, chart data.
    """
    posts = db.query(SurplusPost).filter(SurplusPost.mess_id == mess_id).all()
    total_kg_donated = sum(p.quantity_kg for p in posts)
    
    # Heuristics for environmental impact:
    # 1 kg of food waste = ~2.5 kg CO2 equivalent
    # 1 meal = ~0.4 kg of food
    co2_saved_kg = total_kg_donated * 2.5
    meals_donated = int(total_kg_donated / 0.4)
    
    # ESG Score (mock formula based on donations)
    base_esg = 65
    esg_score = min(98, base_esg + (total_kg_donated * 0.1))

    # Real Trend Data for 6 Months
    df = pd.DataFrame([{
        "created_at": p.created_at,
        "quantity_kg": p.quantity_kg
    } for p in posts if p.created_at])
    
    if not df.empty:
        # Group by Year-Month
        df['month_year'] = df['created_at'].dt.to_period('M')
        monthly_totals = df.groupby('month_year')['quantity_kg'].sum().reset_index()
        monthly_totals = monthly_totals.sort_values('month_year').tail(6)
        
        trend_labels = monthly_totals['month_year'].dt.strftime('%b').tolist()
        trend_data = monthly_totals['quantity_kg'].tolist()
        
        # If less than 6 months of data exists, pad with 0s at the start
        while len(trend_labels) < 6:
            trend_labels.insert(0, "-")
            trend_data.insert(0, 0.0)
    else:
        trend_labels = ["-"] * 6
        trend_data = [0.0] * 6

    return {
        "kg_avoided": round(total_kg_donated, 1),
        "co2_saved": round(co2_saved_kg, 1),
        "meals_donated": meals_donated,
        "esg_score": round(esg_score, 1),
        "trend_labels": trend_labels,
        "trend_data": [round(x, 1) for x in trend_data]
    }

# --- NEW ENDPOINTS: Data Export & Reports ---
@app.get("/api/reports/attendance/csv")
def export_attendance_csv(mess_id: int, db: Session = Depends(get_db)):
    records = db.query(AttendanceRecord).filter(AttendanceRecord.mess_id == mess_id).order_by(AttendanceRecord.date.desc()).all()
    
    stream = io.StringIO()
    writer = csv.writer(stream)
    writer.writerow(["ID", "Date", "Day", "Meal Type", "Expected Students", "Actual Attendance", "Wasted Qty"])
    for r in records:
        writer.writerow([r.id, r.date, r.day_of_week, r.meal_type, r.expected_students, r.actual_attendance, r.wasted_qty])
    
    response = StreamingResponse(iter([stream.getvalue()]), media_type="text/csv")
    response.headers["Content-Disposition"] = "attachment; filename=attendance_report.csv"
    return response

@app.get("/api/reports/waste/csv")
def export_waste_csv(mess_id: int, db: Session = Depends(get_db)):
    records = db.query(SurplusPost).filter(SurplusPost.mess_id == mess_id).order_by(SurplusPost.created_at.desc()).all()
    
    stream = io.StringIO()
    writer = csv.writer(stream)
    writer.writerow(["ID", "Meal Description", "Quantity (kg)", "Expiry Time", "Status", "Created At"])
    for r in records:
        writer.writerow([r.id, r.meal_description, r.quantity_kg, r.expiry_time, r.status, r.created_at])
    
    response = StreamingResponse(iter([stream.getvalue()]), media_type="text/csv")
    response.headers["Content-Disposition"] = "attachment; filename=waste_report.csv"
    return response

@app.get("/api/reports/weekly/csv")
def export_weekly_report(mess_id: int, db: Session = Depends(get_db)):
    records = db.query(AttendanceRecord).filter(AttendanceRecord.mess_id == mess_id).order_by(AttendanceRecord.date.desc()).limit(21).all()
    
    stream = io.StringIO()
    writer = csv.writer(stream)
    writer.writerow(["Date", "Meal Type", "Expected", "Actual", "Difference"])
    for r in records:
        diff = (r.expected_students or 0) - (r.actual_attendance or 0)
        writer.writerow([r.date, r.meal_type, r.expected_students, r.actual_attendance, diff])
    
    response = StreamingResponse(iter([stream.getvalue()]), media_type="text/csv")
    response.headers["Content-Disposition"] = "attachment; filename=weekly_report.csv"
    return response

@app.delete("/api/settings/clear-attendance")
def clear_attendance(mess_id: int, db: Session = Depends(get_db)):
    db.query(AttendanceRecord).filter(AttendanceRecord.mess_id == mess_id).delete()
    db.commit()
    return {"status": "success", "message": "Attendance records cleared"}

# --- NEW ENDPOINT: Dashboard Summary ---
@app.get("/api/dashboard-summary")
def get_dashboard_summary(mess_id: int, db: Session = Depends(get_db)):
    """
    Returns real-time KPI data for the admin dashboard:
    - today_predicted: sum of expected_students for today's records
    - today_actual: sum of actual_attendance for today's records
    - surplus_kg: estimated surplus (predicted - actual) * 0.25 kg
    - ngo_accepted: count of ACCEPTED surplus posts today
    - ngo_pending: count of PENDING surplus recipients today
    - total_donations_kg: total kg donated all time
    - recent_broadcasts: last 3 surplus posts with status
    """
    from models import NGOProfile
    from datetime import date

    today = str(date.today())

    # Today's attendance records
    today_records = db.query(AttendanceRecord).filter(
        AttendanceRecord.mess_id == mess_id,
        AttendanceRecord.date == today
    ).all()

    today_predicted = sum(r.expected_students or 0 for r in today_records)
    today_actual = sum(r.actual_attendance or 0 for r in today_records)
    surplus_kg = max(0, round((today_predicted - today_actual) * 0.25, 1))

    # All-time donations
    all_posts = db.query(SurplusPost).filter(SurplusPost.mess_id == mess_id).all()
    total_donations_kg = round(sum(p.quantity_kg for p in all_posts), 1)

    # Today's donation status
    today_posts = [p for p in all_posts if p.created_at and str(p.created_at.date()) == today]
    today_post_ids = [p.id for p in today_posts]

    ngo_accepted = 0
    ngo_pending = 0
    if today_post_ids:
        recipients = db.query(SurplusRecipient).filter(
            SurplusRecipient.surplus_id.in_(today_post_ids)
        ).all()
        ngo_accepted = sum(1 for r in recipients if r.status == "ACCEPTED")
        ngo_pending = sum(1 for r in recipients if r.status == "PENDING")

    # Recent broadcasts (last 3)
    recent_posts = sorted(all_posts, key=lambda p: p.id, reverse=True)[:3]
    recent_broadcasts = []
    for p in recent_posts:
        ngo_count = db.query(SurplusRecipient).filter(SurplusRecipient.surplus_id == p.id).count()
        recent_broadcasts.append({
            "id": p.id,
            "meal_description": p.meal_description,
            "quantity_kg": p.quantity_kg,
            "status": p.status,
            "created_at": str(p.created_at),
            "ngo_count": ngo_count
        })

    return {
        "today_predicted": today_predicted,
        "today_actual": today_actual,
        "surplus_kg": surplus_kg,
        "ngo_accepted": ngo_accepted,
        "ngo_pending": ngo_pending,
        "total_donations_kg": total_donations_kg,
        "recent_broadcasts": recent_broadcasts
    }

# 7. Chat Endpoints
@app.post("/api/chat")
async def post_chat_message(req: ChatRequest, db: Session = Depends(get_db)):
    msg = ChatMessage(mess_id=req.mess_id, ngo_id=req.ngo_id, sender_type=req.sender_type, message=req.message)
    db.add(msg)
    db.commit()
    db.refresh(msg)
    
    await manager.broadcast({
        "type": "CHAT_MESSAGE",
        "data": {
            "id": msg.id,
            "mess_id": msg.mess_id,
            "ngo_id": msg.ngo_id,
            "sender_type": msg.sender_type,
            "message": msg.message,
            "timestamp": str(msg.created_at) if msg.created_at else ""
        }
    })
    return {"status": "sent"}

@app.get("/api/chat-history")
def get_chat_history(mess_id: int, ngo_id: int, db: Session = Depends(get_db)):
    msgs = db.query(ChatMessage).filter(
        ChatMessage.mess_id == mess_id, 
        ChatMessage.ngo_id == ngo_id
    ).order_by(ChatMessage.id.asc()).limit(100).all()
    
    return [{"id": m.id, "sender_type": m.sender_type, "message": m.message, "timestamp": str(m.created_at)} for m in msgs]

# Profile Endpoints
from models import NGOProfile, MessProfile, User

@app.get("/api/ngos")
def get_all_ngos(db: Session = Depends(get_db)):
    ngos = db.query(NGOProfile).all()
    return [{"id": n.user_id, "name": n.ngo_name, "location": n.location} for n in ngos]

@app.get("/api/messes")
def get_all_messes(db: Session = Depends(get_db)):
    messes = db.query(MessProfile).all()
    return [{"id": m.user_id, "name": m.org_name, "location": m.location} for m in messes]

# Accept a donation (NGO marks a specific surplus as accepted)
@app.post("/api/accept-donation")
async def accept_donation(surplus_id: int, ngo_id: int, db: Session = Depends(get_db)):
    recipient = db.query(SurplusRecipient).filter(
        SurplusRecipient.surplus_id == surplus_id,
        SurplusRecipient.ngo_id == ngo_id
    ).first()
    if recipient:
        recipient.status = "ACCEPTED"
        db.commit()
    surplus = db.query(SurplusPost).filter(SurplusPost.id == surplus_id).first()
    if surplus:
        surplus.status = "ACCEPTED"
        db.commit()
    await manager.broadcast({
        "type": "DONATION_ACCEPTED",
        "data": {"surplus_id": surplus_id, "ngo_id": ngo_id}
    })
    return {"status": "accepted"}

# 8. WebSocket Endpoint
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)