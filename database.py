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
    try:
        return pymysql.connect(**DB_CONFIG)
    except pymysql.err.OperationalError as exc:
        raise RuntimeError(
            "Không thể kết nối tới MySQL. Hãy bật XAMPP -> MySQL và import file database_schema.sql vào database 'pisq'."
        ) from exc

def hash_password(password: str) -> str:
    """Băm mật khẩu dạng SHA256 an toàn."""
    return hashlib.sha256(password.strip().encode('utf-8')).hexdigest()


def ensure_exam_class_column(cursor) -> None:
    cursor.execute("""
        SELECT COUNT(*) AS column_count
        FROM information_schema.columns
        WHERE table_schema = DATABASE()
          AND table_name = 'exams'
          AND column_name = 'class_id'
    """)
    if cursor.fetchone()["column_count"]:
        return

    cursor.execute("""
        ALTER TABLE exams
        ADD COLUMN class_id INT(10) UNSIGNED DEFAULT NULL AFTER creator_id,
        ADD KEY idx_exams_class (class_id),
        ADD CONSTRAINT fk_exams_class
            FOREIGN KEY (class_id) REFERENCES classes (id)
    """)


def ensure_submission_drive_upload_columns(cursor) -> None:
    cursor.execute("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = DATABASE()
          AND table_name = 'exam_submissions'
    """)
    existing_columns = {row["column_name"] for row in cursor.fetchall()}
    columns = {
        "drive_upload_status": "VARCHAR(20) DEFAULT NULL",
        "drive_upload_detail": "TEXT DEFAULT NULL",
        "drive_file_id": "VARCHAR(255) DEFAULT NULL",
        "drive_file_url": "TEXT DEFAULT NULL",
        "drive_upload_attempts": "INT UNSIGNED NOT NULL DEFAULT 0",
    }
    for column_name, definition in columns.items():
        if column_name not in existing_columns:
            cursor.execute(
                f"ALTER TABLE exam_submissions ADD COLUMN {column_name} {definition}"
            )


def init_default_data():
    """Khởi tạo dữ liệu mẫu nếu hệ thống chưa có tài khoản admin hoặc lớp học."""
    conn = None
    is_production = os.getenv("ENVIRONMENT", "").lower() == "production"
    try:
        conn = get_db()
        with conn.cursor() as cursor:
            ensure_exam_class_column(cursor)
            ensure_submission_drive_upload_columns(cursor)

            # 1. Kiểm tra tài khoản admin
            cursor.execute("SELECT id FROM users WHERE role = 'admin' LIMIT 1")
            admin = cursor.fetchone()
            admin_id = None
            if not admin:
                admin_password = os.getenv("ADMIN_DEFAULT_PASSWORD")
                if not admin_password:
                    if is_production:
                        raise RuntimeError(
                            "Cần cấu hình ADMIN_DEFAULT_PASSWORD trước khi tạo admin trên production."
                        )
                    admin_password = "admin123"
                pwd = hash_password(admin_password)
                cursor.execute(
                    """
                    INSERT INTO users (username, password_hash, full_name, role, is_active)
                    VALUES (%s, %s, %s, 'admin', 1)
                    """,
                    ("admin", pwd, "Quản trị viên")
                )
                admin_id = cursor.lastrowid
                print(f"[INIT] Đã tạo tài khoản admin mặc định (ID: {admin_id})")
            else:
                admin_id = admin['id']

            # 2. Kiểm tra lớp học mẫu
            cursor.execute("SELECT id FROM classes LIMIT 1")
            cls = cursor.fetchone()
            class_id = None
            if cls:
                class_id = cls["id"]
            elif not is_production:
                cursor.execute(
                    """
                    INSERT INTO classes (name, grade_level, school_year)
                    VALUES (%s, %s, %s)
                    """,
                    ("12A1", 12, "2024-2025")
                )
                class_id = cursor.lastrowid
                print(f"[INIT] Đã tạo lớp mẫu: 12A1 (ID: {class_id})")

            # 3. Tạo học sinh mẫu "Nguyễn Văn An" khớp đúng với ảnh mockup trong tài liệu
            cursor.execute("SELECT id FROM users WHERE username = 'nguyenvanan' LIMIT 1")
            hs = cursor.fetchone()
            if not hs and not is_production and class_id is not None:
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
        if conn is not None:
            try:
                conn.rollback()
            except Exception:
                pass
        print(f"[INIT ERROR] Lỗi khởi tạo dữ liệu mẫu: {e}")
        print("[INIT] MySQL chưa được khởi động hoặc database 'pisq' chưa được tạo. Hãy bật XAMPP -> MySQL và import database_schema.sql.")
    finally:
        if conn is not None:
            conn.close()

if __name__ == "__main__":
    init_default_data()
