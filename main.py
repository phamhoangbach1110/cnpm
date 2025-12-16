import re
import uvicorn
from json import dumps as json_dumps
from fastapi import FastAPI, Request, Depends, HTTPException, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.orm import sessionmaker, declarative_base, Session

# =========================
# 1. CẤU HÌNH DATABASE
# =========================
SQLALCHEMY_DATABASE_URL = "sqlite:///./database.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Student(Base):
    __tablename__ = "students"
    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(String, unique=True)
    full_name = Column(String)
    dob = Column(String)
    status = Column(String)

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    password = Column(String)
    email = Column(String, unique=True) 
    phone = Column(String) 
    role = Column(String, default="student") 

class Classroom(Base):
    __tablename__ = "classrooms"
    id = Column(Integer, primary_key=True, index=True)
    room_name = Column(String, unique=True, index=True) 
    capacity = Column(Integer)                         
    equipment = Column(String)                        
    status = Column(String, default="Available")

class Booking(Base):
    __tablename__ = "bookings"
    id = Column(Integer, primary_key=True, index=True)
    room_id = Column(Integer)
    user_id = Column(Integer)
    booker_name = Column(String) 
    start_time = Column(String) 
    duration_hours = Column(String)
    status = Column(String, default="Confirmed")

Base.metadata.create_all(bind=engine)

# =========================
# 2. KHỞI TẠO FASTAPI
# =========================
app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

def to_json(obj): 
    return json_dumps(obj)
templates.env.filters['tojson'] = to_json

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# === SỰ KIỆN KHỞI ĐỘNG ===
@app.on_event("startup")
def startup_event():
    db = SessionLocal()
    if not db.query(User).filter(User.username == "admin").first():
        db.add(User(username="admin", password="123", role="admin"))
        print(">>> [INIT] Đã tạo tài khoản mẫu: admin / 123")
    
    if not db.query(Classroom).first():
        rooms = [
            Classroom(room_name="Phòng A101", capacity=40, equipment="Máy chiếu", status="Available"),
            Classroom(room_name="Phòng A102", capacity=40, equipment="Máy chiếu", status="Available"),
            Classroom(room_name="Phòng B201", capacity=50, equipment="Loa, Mic", status="Available"),
            Classroom(room_name="Phòng Lab 1", capacity=30, equipment="PC", status="Available"),
            Classroom(room_name="Hội trường", capacity=100, equipment="Full", status="Available"),
        ]
        db.add_all(rooms)
        db.commit()
        print(">>> [INIT] Đã tạo 5 phòng học mẫu")
    db.close()

def get_current_user(request: Request, db: Session = Depends(get_db)):
    username = request.cookies.get("current_user")
    if not username: return None
    user = db.query(User).filter(User.username == username).first()
    return user

def require_admin(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user or user.role != "admin":
        raise HTTPException(status_code=403, detail="Cần quyền Admin.")
    return user

# =========================
# 3. ROUTE API
# =========================
@app.post("/api/register")
async def register(data: dict, db: Session = Depends(get_db)):
    if db.query(User).filter(User.username == data['username']).first():
        return {"status": "error", "message": "User tồn tại"}
    new_user = User(username=data['username'], password=data['password'], role=data.get('role', 'student'))
    db.add(new_user)
    db.commit()
    return {"status": "success"}

@app.post("/api/login")
async def login(data: dict, response: Response, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == data['username'], User.password == data['password']).first()
    if user:
        response.set_cookie(key="current_user", value=user.username)
        return {"status": "success"}
    return {"status": "error", "message": "Sai tài khoản"}

@app.post("/api/bookings/create")
async def create_booking(data: dict, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    new_booking = Booking(
        room_id=data['room_id'],
        user_id=current_user.id, 
        booker_name=current_user.username, 
        start_time=data['start_time'],
        duration_hours=data['duration_display'], 
        status="Confirmed"
    )
    db.add(new_booking)
    
    # Cập nhật trạng thái phòng thành Occupied
    room = db.query(Classroom).filter(Classroom.id == data['room_id']).first()
    if room: room.status = "Occupied"
    
    db.commit()
    return {"status": "success", "message": "Đặt lịch thành công!"}

# API XÓA LỊCH ĐẶT (MỚI)
@app.post("/api/bookings/delete")
async def delete_booking(data: dict, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    booking = db.query(Booking).filter(Booking.id == data['booking_id']).first()
    if not booking:
        return {"status": "error", "message": "Không tìm thấy lịch đặt."}
    
    room_id = booking.room_id
    db.delete(booking)
    
    # Kiểm tra xem phòng còn lịch nào khác trong tương lai gần không (để reset status)
    # Đơn giản hóa: Set lại Available sau khi hủy
    room = db.query(Classroom).filter(Classroom.id == room_id).first()
    if room: room.status = "Available"
    
    db.commit()
    return {"status": "success", "message": "Đã hủy lịch đặt thành công!"}

# =========================
# 4. ROUTE HIỂN THỊ
# =========================
@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user: return RedirectResponse("/")
    return templates.TemplateResponse("index.html", {
        "request": request, "username": user.username, "role": user.role,
        "students": db.query(Student).all(), "classrooms": db.query(Classroom).all()
    })

@app.get("/logout")
async def logout(response: Response):
    response = RedirectResponse("/")
    response.delete_cookie("current_user")
    return response

@app.get("/room-management", response_class=HTMLResponse)
async def room_management(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user or user.role != "admin": return RedirectResponse("/dashboard")
    return templates.TemplateResponse("room_management.html", {
        "request": request, "classrooms": db.query(Classroom).all(), "username": user.username, "role": user.role
    })

@app.get("/booking-scheduler", response_class=HTMLResponse)
async def booking_scheduler(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user or user.role != "admin": return RedirectResponse("/dashboard")

    # Lấy thêm ID của booking để phục vụ việc xóa
    classrooms_list = [{"id": c.id, "room_name": c.room_name, "capacity": c.capacity} for c in db.query(Classroom).all()]
    
    bookings_data = db.query(
        Booking.id, # <--- Thêm ID
        Booking.room_id, 
        Booking.booker_name, 
        Booking.start_time, 
        Booking.duration_hours
    ).all()
    
    bookings_list = [
        {
            "id": b[0], 
            "room_id": b[1], 
            "booker_name": b[2], 
            "start_time": b[3], 
            "duration_hours": b[4]
        } for b in bookings_data
    ]

    return templates.TemplateResponse("booking_scheduler.html", {
        "request": request, "classrooms": classrooms_list, "bookings": bookings_list,
        "username": user.username, "role": user.role
    })

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)