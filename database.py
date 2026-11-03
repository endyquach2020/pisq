import os
import hashlib
import pymysql
from pymysql.cursors import DictCursor

# Đọc cấu hình từ biến môi trường (Environment Variables)
# Giúp chạy mượt mà cả ở Local XAMPP lẫn khi đưa lên GitHub / Hosting Cloud MySQL
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 3306)),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", ""),  # XAMPP mặc định để trống
    "database": os.getenv("DB_NAME", "pisq"),
    "charset": "utf8mb4",
    "cursorclass": DictCursor
}

def get_db():
    return pymysql.connect(**DB_CONFIG)

def hash_password(password: str) -> str:
    """Băm mật khẩu dạng SHA256 an toàn."""
    return hashlib.sha256(password.strip().encode('utf-8')).hexdigest()

def init_default_data():
    """Khởi tạo dữ liệu mẫu nếu hệ thống chưa có tài khoản admin hoặc lớp học."""
    conn = get_db()
    try:
        with conn.cursor() as cursor:
            # 1. Kiểm tra tài khoản admin
            cursor.execute("SELECT id FROM users WHERE role = 'admin' LIMIT 1")
            admin = cursor.fetchone()
            admin_id = None
            if not admin:
                pwd = hash_password("admin123")
                cursor.execute(
                    """
                    INSERT INTO users (username, password_hash, full_name, role, is_active)
                    VALUES (%s, %s, %s, 'admin', 1)
                    """,
                    ("admin", pwd, "Quản trị viên")
                )
                admin_id = cursor.lastrowid
                print(f"[INIT] Đã tạo tài khoản admin mặc định: admin / admin123 (ID: {admin_id})")
            else:
                admin_id = admin['id']

            # 2. Kiểm tra lớp học mẫu
            cursor.execute("SELECT id FROM classes LIMIT 1")
            cls = cursor.fetchone()
            class_id = None
            if not cls:
                cursor.execute(
                    """
                    INSERT INTO classes (name, grade_level, school_year)
                    VALUES (%s, %s, %s)
                    """,
                    ("12A1", 12, "2024-2025")
                )
                class_id = cursor.lastrowid
                print(f"[INIT] Đã tạo lớp mẫu: 12A1 (ID: {class_id})")
            else:
                class_id = cls['id']

            # 3. Tạo học sinh mẫu "Nguyễn Văn An" khớp đúng với ảnh mockup trong tài liệu
            cursor.execute("SELECT id FROM users WHERE username = 'nguyenvanan' LIMIT 1")
            hs = cursor.fetchone()
            if not hs:
                hs_pwd = hash_password("123456")
                cursor.execute(
                    """
                    INSERT INTO users (class_id, username, password_hash, full_name, role, gender, is_active)
                    VALUES (%s, %s, %s, %s, 'student', 'male', 1)
                    """,
                    (class_id, "nguyenvanan", hs_pwd, "Nguyễn Văn An")
                )
                print("[INIT] Đã tạo học sinh mẫu: nguyenvanan / 123456 (Họ tên: Nguyễn Văn An)")

        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"[INIT ERROR] Lỗi khởi tạo dữ liệu mẫu: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    init_default_data()
