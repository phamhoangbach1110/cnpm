#.\venv\Scripts\activate: kich hoat venv
from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, Date
from sqlalchemy.orm import sessionmaker, declarative_base, Session

from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime

# bảo mật / authentication helpers
from passlib.context import CryptContext
from itsdangerous import URLSafeSerializer, BadSignature
from fastapi import Form, status
from fastapi.responses import RedirectResponse

from typing import Optional

SECRET_KEY = "thay_bang_chuoi_bi_mat_cua_ban"  # đổi sang secret thực tế (env)
SESSION_COOKIE = "r_session"
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
serializer = URLSafeSerializer(SECRET_KEY, salt="session-salt")

# =========================
#  Cấu hình DB SQLite
# =========================
SQLALCHEMY_DATABASE_URL = "sqlite:///./database.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class Booking(Base):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, index=True)
    room_name = Column(String, index=True)
    date = Column(Date, index=True)
    start_time = Column(String)
    end_time = Column(String)
    purpose = Column(String)

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    is_active = Column(Integer, default=1)

Base.metadata.create_all(bind=engine)

class BookingCreate(BaseModel):
    room_name: str
    date: str
    start_time: str
    end_time: str
    purpose: str

# ----- password & session helpers -----
def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)

def create_session_cookie(username: str) -> str:
    return serializer.dumps({"username": username})

def load_session_cookie(cookie_value: str):
    try:
        data = serializer.loads(cookie_value)
        return data
    except BadSignature:
        return None

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

app = FastAPI()

def get_current_user(request: Request, db: Session = Depends(get_db)) -> Optional[User]:
    cookie = request.cookies.get(SESSION_COOKIE)
    if not cookie:
        return None
    data = load_session_cookie(cookie)
    if not data or "username" not in data:
        return None
    user = db.query(User).filter(User.username == data["username"]).first()
    return user

def require_user(user: User = Depends(get_current_user)):
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    return user

# CORS (dự phòng nếu chạy frontend ở port khác)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

@app.get("/", response_class=HTMLResponse)
def home(request: Request, user: User = Depends(require_user)):
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "current_user": user}
    )

@app.post("/api/bookings")
def create_booking(booking: BookingCreate, db: Session = Depends(get_db)):
    try:
        booking_date = datetime.strptime(booking.date, "%Y-%m-%d").date()
    except:
        raise HTTPException(status_code=400, detail="Ngày không đúng định dạng.")

    existing = (
        db.query(Booking)
        .filter(Booking.room_name == booking.room_name)
        .filter(Booking.date == booking_date)
        .all()
    )

    for b in existing:
        if not (booking.end_time <= b.start_time or booking.start_time >= b.end_time):
            raise HTTPException(
                status_code=400,
                detail="Khung giờ này đã có người đặt rồi!"
            )

    new_booking = Booking(
        room_name=booking.room_name,
        date=booking_date,
        start_time=booking.start_time,
        end_time=booking.end_time,
        purpose=booking.purpose,
    )
    db.add(new_booking)
    db.commit()
    db.refresh(new_booking)

    return {
        "id": new_booking.id,
        "room_name": new_booking.room_name,
        "date": str(new_booking.date),
        "start_time": new_booking.start_time,
        "end_time": new_booking.end_time,
        "purpose": new_booking.purpose,
    }

@app.get("/api/bookings")
def get_bookings(date: str, db: Session = Depends(get_db)):
    """Lấy tất cả lịch đặt phòng theo ngày"""
    try:
        booking_date = datetime.strptime(date, "%Y-%m-%d").date()
    except:
        raise HTTPException(status_code=400, detail="Sai định dạng ngày")

    bookings = db.query(Booking).filter(Booking.date == booking_date).all()
    return [
        {
            "id": b.id,
            "room_name": b.room_name,
            "start_time": b.start_time,
            "end_time": b.end_time,
            "purpose": b.purpose,
        }
        for b in bookings
    ]

@app.delete("/api/bookings/{booking_id}")
def delete_booking(booking_id: int, db: Session = Depends(get_db)):
    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Không tìm thấy đặt phòng")

    db.delete(booking)
    db.commit()
    return {"message": "Đã xóa đặt phòng"}

# --- Login form ---
@app.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
def login_action(request: Request, username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == username).first()
    if not user or not verify_password(password, user.hashed_password) or not user.is_active:
        return templates.TemplateResponse("login.html", {"request": request, "error": "Tên đăng nhập hoặc mật khẩu không đúng."})

    cookie_val = create_session_cookie(user.username)
    response = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    response.set_cookie(SESSION_COOKIE, cookie_val, httponly=True, samesite="lax")
    return response

@app.get("/logout")
def logout():
    response = RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    response.delete_cookie(SESSION_COOKIE)
    return response
