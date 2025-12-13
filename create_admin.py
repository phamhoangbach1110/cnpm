from main import SessionLocal, User, hash_password

db = SessionLocal()
username = "admin"
password = "admin123"

u = User(username=username, hashed_password=hash_password(password), is_active=1)
db.add(u)

try:
    db.commit()
    print("Tạo tài khoản thành công!")
    print("Username:", username)
    print("Password:", password)
except Exception as e:
    db.rollback()
    print("Lỗi:", e)
finally:
    db.close()
