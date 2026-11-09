import os
import re
import json
import asyncio
import random
import secrets
import time
import datetime
import unicodedata
from typing import Optional, List
import openpyxl
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

import database
from database import get_db, hash_password
from docx_parser import parse_docx_file, UPLOAD_DIR
from google_drive import (
    DriveConfigurationError,
    DriveUploadError,
    upload_pdf_to_drive,
)
from results_export import build_student_submission_pdf

app = FastAPI(title="PisQ Exam System", version="2.0.0")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=int(os.getenv("PORT", "3000")), reload=True)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Đảm bảo thư mục static và uploads tồn tại
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(STATIC_DIR, exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.on_event("startup")
def startup_event():
    # Khởi tạo dữ liệu mẫu nếu DB trống
    try:
        database.init_default_data()
        with get_db() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    UPDATE exam_submissions
                    SET drive_upload_status = 'pending',
                        drive_upload_attempts = 0
                    WHERE drive_upload_status = 'uploading'
                """)
            conn.commit()
        asyncio.create_task(submission_drive_upload_worker())
    except Exception as exc:
        print(f"[STARTUP] Không thể khởi tạo dữ liệu mặc định: {exc}")

@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"status": "error", "detail": exc.detail}
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request, exc: Exception):
    detail = str(exc) if str(exc) else "Lỗi máy chủ không xác định."
    return JSONResponse(
        status_code=500,
        content={"status": "error", "detail": detail}
    )


# ==================== DATA SCHEMAS ====================
class LoginRequest(BaseModel):
    username: str
    password: str
    role: Optional[str] = None  # 'admin' / 'teacher' / 'student'

class CreateClassRequest(BaseModel):
    name: str
    grade_level: int
    school_year: Optional[str] = "2024-2025"

class CreateStudentRequest(BaseModel):
    username: str
    full_name: str
    password: str
    class_id: int
    gender: Optional[str] = "other"
    date_of_birth: Optional[str] = None

class ResetStudentPasswordRequest(BaseModel):
    admin_username: str
    admin_password: str

class ExamConfigSection(BaseModel):
    id: int
    points: float
    shuffle_questions: Optional[int] = 1
    shuffle_options: Optional[int] = 1

class UpdateExamConfigRequest(BaseModel):
    title: str
    duration_minutes: int
    total_score: float
    is_published: int
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    sections: Optional[List[ExamConfigSection]] = []

class SaveAnswerRequest(BaseModel):
    question_id: int
    selected_option_id: Optional[int] = None
    text_answer: Optional[str] = None
    tf_answers: Optional[dict] = None  # { "option_id": "true" | "false" }

class QuestionOptionInput(BaseModel):
    id: Optional[int] = None
    option_label: Optional[str] = None
    content: str
    is_correct: Optional[int] = 0
    order_index: Optional[int] = 1

class UpdateQuestionRequest(BaseModel):
    content: str
    points: Optional[float] = None
    explanation: Optional[str] = None
    options: Optional[List[QuestionOptionInput]] = None

class CreateQuestionRequest(BaseModel):
    content: str
    points: Optional[float] = 0.25
    explanation: Optional[str] = ""
    options: Optional[List[QuestionOptionInput]] = []

# ==================== AUTHENTICATION APIS ====================
@app.post("/api/auth/login")
def login(req: LoginRequest):
    pwd_hash = hash_password(req.password)
    conn = get_db()
    try:
        with conn.cursor() as cursor:
            query = "SELECT u.*, c.name as class_name FROM users u LEFT JOIN classes c ON u.class_id = c.id WHERE u.username = %s AND u.password_hash = %s AND u.is_active = 1"
            cursor.execute(query, (req.username.strip(), pwd_hash))
            user = cursor.fetchone()
            if not user:
                raise HTTPException(status_code=401, detail="Tên đăng nhập hoặc mật khẩu không chính xác!")

            # Nếu người dùng chọn tab role cụ thể, kiểm tra khớp
            if req.role and req.role == 'admin' and user['role'] not in ['admin', 'teacher']:
                raise HTTPException(status_code=403, detail="Tài khoản này không có quyền Quản trị / Giáo viên!")

            return {
                "status": "success",
                "message": "Đăng nhập thành công!",
                "user": {
                    "id": user["id"],
                    "username": user["username"],
                    "full_name": user["full_name"],
                    "role": user["role"],
                    "class_id": user["class_id"],
                    "class_name": user["class_name"]
                }
            }
    finally:
        conn.close()

# ==================== ADMIN: LỚP HỌC & HỌC SINH ====================
@app.get("/api/admin/classes")
def get_classes():
    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT c.*, COUNT(u.id) as student_count 
                FROM classes c 
                LEFT JOIN users u ON u.class_id = c.id AND u.role = 'student'
                GROUP BY c.id
                ORDER BY c.grade_level ASC, c.name ASC
            """)
            classes = cursor.fetchall()
            return {"status": "success", "classes": classes}
    finally:
        conn.close()

@app.post("/api/admin/classes")
def create_class(req: CreateClassRequest):
    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO classes (name, grade_level, school_year) VALUES (%s, %s, %s)",
                (req.name.strip(), req.grade_level, req.school_year.strip())
            )
            class_id = cursor.lastrowid
        conn.commit()
        return {"status": "success", "message": "Thêm lớp học thành công!", "class_id": class_id}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()

@app.get("/api/admin/students")
def get_students(class_id: Optional[int] = None):
    conn = get_db()
    try:
        with conn.cursor() as cursor:
            if class_id:
                cursor.execute("""
                    SELECT u.id, u.username, u.full_name, u.role, u.date_of_birth, u.gender, u.is_active, c.name as class_name, c.id as class_id
                    FROM users u 
                    LEFT JOIN classes c ON u.class_id = c.id 
                    WHERE u.role = 'student' AND u.class_id = %s
                    ORDER BY u.id DESC
                """, (class_id,))
            else:
                cursor.execute("""
                    SELECT u.id, u.username, u.full_name, u.role, u.date_of_birth, u.gender, u.is_active, c.name as class_name, c.id as class_id
                    FROM users u 
                    LEFT JOIN classes c ON u.class_id = c.id 
                    WHERE u.role = 'student'
                    ORDER BY u.id DESC
                """)
            students = cursor.fetchall()
            return {"status": "success", "students": students}
    finally:
        conn.close()


@app.post("/api/admin/students/{student_id}/reset-password")
def reset_student_password(student_id: int, req: ResetStudentPasswordRequest):
    temporary_password = "".join(
        secrets.choice("ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789")
        for _ in range(10)
    )
    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT id FROM users
                WHERE username = %s AND password_hash = %s
                  AND role IN ('admin', 'teacher') AND is_active = 1
                """,
                (req.admin_username.strip(), hash_password(req.admin_password)),
            )
            if not cursor.fetchone():
                raise HTTPException(
                    status_code=403,
                    detail="Xác thực quản trị không thành công.",
                )

            cursor.execute(
                "SELECT id FROM users WHERE id = %s AND role = 'student'",
                (student_id,),
            )
            if not cursor.fetchone():
                raise HTTPException(status_code=404, detail="Không tìm thấy học sinh!")

            cursor.execute(
                "UPDATE users SET password_hash = %s WHERE id = %s AND role = 'student'",
                (hash_password(temporary_password), student_id),
            )
        conn.commit()
        return {
            "status": "success",
            "message": "Đã đặt lại mật khẩu học sinh.",
            "temporary_password": temporary_password,
        }
    except HTTPException:
        conn.rollback()
        raise
    except Exception as exc:
        conn.rollback()
        raise HTTPException(status_code=500, detail="Không thể đặt lại mật khẩu học sinh.") from exc
    finally:
        conn.close()


@app.post("/api/admin/students")
def create_student(req: CreateStudentRequest):
    conn = get_db()
    try:
        with conn.cursor() as cursor:
            # Kiểm tra trùng username
            cursor.execute("SELECT id FROM users WHERE username = %s", (req.username.strip(),))
            if cursor.fetchone():
                raise HTTPException(status_code=400, detail="Tên đăng nhập đã tồn tại trên hệ thống!")

            pwd_hash = hash_password(req.password)
            cursor.execute("""
                INSERT INTO users (class_id, username, password_hash, full_name, role, gender, date_of_birth, is_active)
                VALUES (%s, %s, %s, %s, 'student', %s, %s, 1)
            """, (req.class_id, req.username.strip(), pwd_hash, req.full_name.strip(), req.gender, req.date_of_birth or None))
            sid = cursor.lastrowid
        conn.commit()
        return {"status": "success", "message": "Thêm học sinh thành công!", "student_id": sid}
    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@app.post("/api/admin/students/import-excel")
async def import_students_excel(
    class_id: int = Form(...),
    file: UploadFile = File(...)
):
    """
    Import danh sách học sinh từ file Excel (.xlsx).
    Cột yêu cầu:
    Cột 1: Tên đăng nhập (Username)
    Cột 2: Họ và tên (Full Name)
    Cột 3: Mật khẩu (Password - mặc định 123456 nếu trống)
    Cột 4: Giới tính (Nam / Nữ / Khác)
    """
    if not (file.filename.endswith(".xlsx") or file.filename.endswith(".xls")):
        raise HTTPException(status_code=400, detail="Chỉ hỗ trợ file Excel định dạng .xlsx")

    temp_path = os.path.join(UPLOAD_DIR, f"excel_{datetime.datetime.now().timestamp()}_{file.filename}")
    try:
        with open(temp_path, "wb") as f:
            f.write(await file.read())

        wb = openpyxl.load_workbook(temp_path)
        sheet = wb.active
        imported_count = 0

        conn = get_db()
        with conn.cursor() as cursor:
            # Duyệt từ dòng 2 (bỏ qua dòng tiêu đề header)
            for row in sheet.iter_rows(min_row=2, values_only=True):
                if not row or not row[0]:
                    continue
                username = str(row[0]).strip()
                full_name = str(row[1]).strip() if len(row) > 1 and row[1] else username
                password = str(row[2]).strip() if len(row) > 2 and row[2] else "123456"
                gender_str = str(row[3]).strip().lower() if len(row) > 3 and row[3] else "other"
                gender = "male" if "nam" in gender_str else ("female" if "nữ" in gender_str else "other")

                pwd_hash = hash_password(password)
                # Chèn hoặc cập nhật
                cursor.execute("""
                    INSERT INTO users (class_id, username, password_hash, full_name, role, gender, is_active)
                    VALUES (%s, %s, %s, %s, 'student', %s, 1)
                    ON DUPLICATE KEY UPDATE 
                        full_name = VALUES(full_name),
                        class_id = VALUES(class_id),
                        password_hash = VALUES(password_hash),
                        gender = VALUES(gender)
                """, (class_id, username, pwd_hash, full_name, gender))
                imported_count += 1

            conn.commit()
            conn.close()

        return {
            "status": "success",
            "message": f"Đã nhập thành công {imported_count} học sinh từ file Excel!",
            "imported_count": imported_count
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi đọc file Excel: {str(e)}")
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

# ==================== ADMIN: QUẢN LÝ ĐỀ THI ====================
@app.get("/api/admin/exams")
def get_all_exams():
    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT e.*, c.name as class_name,
                       COUNT(DISTINCT s.id) as section_count,
                       COUNT(DISTINCT q.id) as question_count,
                       COUNT(DISTINCT sub.id) as submission_count
                FROM exams e
                LEFT JOIN classes c ON c.id = e.class_id
                LEFT JOIN exam_sections s ON s.exam_id = e.id
                LEFT JOIN questions q ON q.section_id = s.id
                LEFT JOIN exam_submissions sub ON sub.exam_id = e.id
                GROUP BY e.id, c.name
                ORDER BY e.id DESC
            """)
            exams = cursor.fetchall()
            return {"status": "success", "exams": exams}
    finally:
        conn.close()

@app.get("/api/admin/exams/{exam_id}")
def get_exam_detail(exam_id: int):
    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM exams WHERE id = %s", (exam_id,))
            exam = cursor.fetchone()
            if not exam:
                raise HTTPException(status_code=404, detail="Không tìm thấy bài thi!")

            cursor.execute("SELECT * FROM exam_sections WHERE exam_id = %s ORDER BY order_index ASC", (exam_id,))
            sections = cursor.fetchall()

            for sec in sections:
                cursor.execute("SELECT * FROM questions WHERE section_id = %s ORDER BY order_index ASC", (sec['id'],))
                questions = cursor.fetchall()
                for q in questions:
                    cursor.execute("SELECT * FROM question_options WHERE question_id = %s ORDER BY order_index ASC", (q['id'],))
                    q['options'] = cursor.fetchall()
                sec['questions'] = questions

            exam['sections'] = sections
            return {"status": "success", "exam": exam}
    finally:
        conn.close()

@app.post("/api/admin/exams/import-docx")
async def import_exam_docx(
    title: str = Form(...),
    class_id: Optional[int] = Form(None),
    duration_minutes: int = Form(45),
    total_score: float = Form(10.0),
    is_published: int = Form(1),
    file: UploadFile = File(...)
):
    if not file.filename.endswith(".docx"):
        raise HTTPException(status_code=400, detail="Vui lòng chỉ tải lên file Word định dạng .docx")
    if class_id is not None:
        if class_id <= 0:
            raise HTTPException(status_code=400, detail="Lớp được chọn không hợp lệ.")

        conn = get_db()
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT id FROM classes WHERE id = %s", (class_id,))
                if not cursor.fetchone():
                    raise HTTPException(status_code=400, detail="Lớp được chọn không tồn tại.")
        finally:
            conn.close()

    temp_path = os.path.join(UPLOAD_DIR, f"temp_{datetime.datetime.now().timestamp()}_{file.filename}")
    try:
        with open(temp_path, "wb") as f:
            f.write(await file.read())

        # Phân tích file Word
        parsed_sections = parse_docx_file(temp_path)
        if not parsed_sections:
            raise HTTPException(status_code=400, detail="Không bóc tách được câu hỏi nào từ file Word. Hãy kiểm tra lại định dạng <#g1>, <#g2>,... và 'Câu X:'")

        conn = get_db()
        with conn.cursor() as cursor:
            # Lấy creator_id (admin đầu tiên)
            cursor.execute("SELECT id FROM users WHERE role = 'admin' LIMIT 1")
            admin_user = cursor.fetchone()
            creator_id = admin_user['id'] if admin_user else 1

            # 1. Thêm vào bảng exams
            cursor.execute("""
                INSERT INTO exams (title, creator_id, class_id, total_score, duration_minutes, is_published)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (title.strip(), creator_id, class_id, total_score, duration_minutes, is_published))
            exam_id = cursor.lastrowid

            # Tính điểm mặc định cho từng phần
            # GDPT 2018 chuẩn: g1: 3.0đ, g2: 4.0đ, g3: 3.0đ (nếu đủ 3 phần)
            num_sections = len(parsed_sections)
            default_weights = {"g1": 3.0, "g2": 4.0, "g3": 3.0, "g4": 3.0}
            total_default_weight = sum(default_weights.get(s["section_type"], 2.5) for s in parsed_sections)
            
            total_questions = 0

            # 2. Thêm từng phần vào exam_sections
            for s_idx, sec in enumerate(parsed_sections):
                s_type = sec["section_type"]
                sec_points = round((default_weights.get(s_type, 2.5) / total_default_weight) * total_score, 2)
                
                # Cờ trộn theo quy tắc GDPT 2018:
                # g1: trộn câu hỏi & phương án
                # g2: giữ nguyên câu hỏi, trộn phương án đúng/sai a, b, c, d
                # g3: trộn câu hỏi
                # g4: không trộn
                shuffle_q = 1 if s_type in ['g1', 'g3'] else 0
                shuffle_opt = 1 if s_type in ['g1', 'g2'] else 0

                cursor.execute("""
                    INSERT INTO exam_sections 
                    (exam_id, section_type, title, order_index, points, shuffle_questions, shuffle_options)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (exam_id, s_type, sec["title"], s_idx + 1, sec_points, shuffle_q, shuffle_opt))
                sec_id = cursor.lastrowid

                # Tính điểm mỗi câu trong phần này
                q_count = len(sec["questions"])
                pts_per_q = round(sec_points / q_count, 2) if q_count > 0 else 0.0

                # 3. Thêm câu hỏi và phương án
                for q_idx, q in enumerate(sec["questions"]):
                    total_questions += 1
                    cursor.execute("""
                        INSERT INTO questions (section_id, content, order_index, points)
                        VALUES (%s, %s, %s, %s)
                    """, (sec_id, q["content"], q_idx + 1, pts_per_q))
                    question_id = cursor.lastrowid

                    # Nếu là câu trắc nghiệm hoặc đúng sai có các options
                    if q["options"]:
                        for o_idx, opt in enumerate(q["options"]):
                            cursor.execute("""
                                INSERT INTO question_options (question_id, option_label, content, is_correct, order_index)
                                VALUES (%s, %s, %s, %s, %s)
                            """, (question_id, opt["label"], opt["content"], 1 if opt["is_correct"] else 0, o_idx + 1))
                    
                    # Nếu có đáp án ngắn (trong phần g3)
                    elif q.get("short_answer"):
                        cursor.execute("""
                            INSERT INTO question_options (question_id, option_label, content, is_correct, order_index)
                            VALUES (%s, %s, %s, 1, 1)
                        """, (question_id, "ANS", q["short_answer"]))

            conn.commit()
            conn.close()

        return {
            "status": "success",
            "message": f"Nạp đề thi thành công! Đã tạo {len(parsed_sections)} phần với {total_questions} câu hỏi.",
            "exam_id": exam_id,
            "total_sections": len(parsed_sections),
            "total_questions": total_questions
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

@app.put("/api/admin/exams/{exam_id}/config")
def update_exam_config(exam_id: int, req: UpdateExamConfigRequest):
    conn = get_db()
    try:
        with conn.cursor() as cursor:
            # 1. Cập nhật thông tin chung đề thi
            cursor.execute("""
                UPDATE exams 
                SET title = %s, duration_minutes = %s, total_score = %s, is_published = %s,
                    start_time = %s, end_time = %s
                WHERE id = %s
            """, (req.title.strip(), req.duration_minutes, req.total_score, req.is_published,
                  req.start_time or None, req.end_time or None, exam_id))

            # 2. Cập nhật điểm và cờ trộn từng phần (nếu gửi lên)
            for sec in req.sections:
                cursor.execute("""
                    UPDATE exam_sections
                    SET points = %s, shuffle_questions = %s, shuffle_options = %s
                    WHERE id = %s AND exam_id = %s
                """, (sec.points, sec.shuffle_questions, sec.shuffle_options, sec.id, exam_id))

                # Tự động chia đều điểm của phần này cho các câu hỏi thuộc phần
                cursor.execute("SELECT id FROM questions WHERE section_id = %s", (sec.id,))
                qs = cursor.fetchall()
                if qs:
                    per_q = round(sec.points / len(qs), 2)
                    cursor.execute("UPDATE questions SET points = %s WHERE section_id = %s", (per_q, sec.id))

            conn.commit()
            return {"status": "success", "message": "Cập nhật cấu hình đề thi thành công!"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@app.delete("/api/admin/exams/{exam_id}")
def delete_exam(exam_id: int):
    conn = get_db()
    try:
        with conn.cursor() as cursor:
            # Xóa các liên kết cascading
            cursor.execute("DELETE FROM exams WHERE id = %s", (exam_id,))
            conn.commit()
            return {"status": "success", "message": "Đã xóa bài thi thành công!"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

# ==================== ADMIN: QUẢN LÝ CÂU HỎI & ĐÁP ÁN ====================
@app.get("/api/admin/exams/{exam_id}/questions")
def get_exam_questions(exam_id: int):
    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id, title, duration_minutes, total_score, is_published FROM exams WHERE id = %s", (exam_id,))
            exam = cursor.fetchone()
            if not exam:
                raise HTTPException(status_code=404, detail="Không tìm thấy bài thi!")

            cursor.execute("SELECT * FROM exam_sections WHERE exam_id = %s ORDER BY order_index ASC", (exam_id,))
            sections = cursor.fetchall()

            total_questions = 0
            for sec in sections:
                cursor.execute("SELECT * FROM questions WHERE section_id = %s ORDER BY order_index ASC", (sec['id'],))
                questions = cursor.fetchall()
                for q in questions:
                    total_questions += 1
                    q['points'] = float(q['points'])
                    cursor.execute("SELECT * FROM question_options WHERE question_id = %s ORDER BY order_index ASC", (q['id'],))
                    q['options'] = cursor.fetchall()
                sec['questions'] = questions

            exam['sections'] = sections
            exam['total_questions'] = total_questions
            return {"status": "success", "exam": exam}
    finally:
        conn.close()

@app.get("/api/admin/questions/{question_id}")
def get_question_detail(question_id: int):
    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT q.*, s.section_type, s.title as section_title, s.exam_id, e.title as exam_title
                FROM questions q
                JOIN exam_sections s ON q.section_id = s.id
                JOIN exams e ON s.exam_id = e.id
                WHERE q.id = %s
            """, (question_id,))
            q = cursor.fetchone()
            if not q:
                raise HTTPException(status_code=404, detail="Không tìm thấy câu hỏi!")

            q['points'] = float(q['points'])
            cursor.execute("SELECT * FROM question_options WHERE question_id = %s ORDER BY order_index ASC", (question_id,))
            q['options'] = cursor.fetchall()
            return {"status": "success", "question": q}
    finally:
        conn.close()

@app.put("/api/admin/questions/{question_id}")
def update_question(question_id: int, req: UpdateQuestionRequest):
    conn = get_db()
    try:
        with conn.cursor() as cursor:
            # 1. Kiểm tra câu hỏi tồn tại
            cursor.execute("""
                SELECT q.*, s.section_type, s.exam_id 
                FROM questions q 
                JOIN exam_sections s ON q.section_id = s.id 
                WHERE q.id = %s
            """, (question_id,))
            existing = cursor.fetchone()
            if not existing:
                raise HTTPException(status_code=404, detail="Không tìm thấy câu hỏi!")

            pts = req.points if req.points is not None else float(existing['points'])
            exp = req.explanation if req.explanation is not None else existing.get('explanation', '')

            # 2. Cập nhật thông tin câu hỏi
            cursor.execute("""
                UPDATE questions 
                SET content = %s, points = %s, explanation = %s
                WHERE id = %s
            """, (req.content.strip(), pts, exp, question_id))

            # 3. Đồng bộ các đáp án / phương án lựa chọn
            if req.options is not None:
                cursor.execute("SELECT id FROM question_options WHERE question_id = %s", (question_id,))
                current_db_opt_ids = {row['id'] for row in cursor.fetchall()}

                kept_opt_ids = set()
                default_labels = ['A', 'B', 'C', 'D', 'E', 'F'] if existing['section_type'] != 'g2' else ['a', 'b', 'c', 'd', 'e', 'f']

                for idx, opt in enumerate(req.options):
                    lbl = opt.option_label or (default_labels[idx] if idx < len(default_labels) else f"OPT_{idx+1}")
                    if existing['section_type'] == 'g1':
                        lbl = default_labels[idx] if idx < len(default_labels) else f"OPT_{idx+1}"
                    lbl = lbl.strip()
                    is_corr = 1 if opt.is_correct else 0

                    if opt.id and opt.id in current_db_opt_ids:
                        cursor.execute("""
                            UPDATE question_options
                            SET option_label = %s, content = %s, is_correct = %s, order_index = %s
                            WHERE id = %s AND question_id = %s
                        """, (lbl, opt.content.strip(), is_corr, idx + 1, opt.id, question_id))
                        kept_opt_ids.add(opt.id)
                    else:
                        cursor.execute("""
                            INSERT INTO question_options (question_id, option_label, content, is_correct, order_index)
                            VALUES (%s, %s, %s, %s, %s)
                        """, (question_id, lbl, opt.content.strip(), is_corr, idx + 1))
                        kept_opt_ids.add(cursor.lastrowid)

                # Xóa những phương án bị gỡ bỏ
                to_delete_ids = current_db_opt_ids - kept_opt_ids
                if to_delete_ids:
                    format_strings = ','.join(['%s'] * len(to_delete_ids))
                    cursor.execute(
                        f"DELETE FROM question_options WHERE id IN ({format_strings}) AND question_id = %s",
                        tuple(to_delete_ids) + (question_id,)
                    )

            conn.commit()
            return {
                "status": "success",
                "message": "Cập nhật câu hỏi và đáp án thành công!",
                "question_id": question_id
            }
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@app.post("/api/admin/sections/{section_id}/questions")
def create_question(section_id: int, req: CreateQuestionRequest):
    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM exam_sections WHERE id = %s", (section_id,))
            sec = cursor.fetchone()
            if not sec:
                raise HTTPException(status_code=404, detail="Không tìm thấy phần thi!")

            cursor.execute("SELECT COALESCE(MAX(order_index), 0) + 1 as next_order FROM questions WHERE section_id = %s", (section_id,))
            next_order = cursor.fetchone()['next_order']

            cursor.execute("""
                INSERT INTO questions (section_id, content, order_index, points, explanation)
                VALUES (%s, %s, %s, %s, %s)
            """, (section_id, req.content.strip(), next_order, req.points, req.explanation or None))
            new_qid = cursor.lastrowid

            default_labels = ['A', 'B', 'C', 'D', 'E', 'F'] if sec['section_type'] != 'g2' else ['a', 'b', 'c', 'd', 'e', 'f']
            if req.options:
                for idx, opt in enumerate(req.options):
                    lbl = opt.option_label or (default_labels[idx] if idx < len(default_labels) else f"OPT_{idx+1}")
                    is_corr = 1 if opt.is_correct else 0
                    cursor.execute("""
                        INSERT INTO question_options (question_id, option_label, content, is_correct, order_index)
                        VALUES (%s, %s, %s, %s, %s)
                    """, (new_qid, lbl.strip(), opt.content.strip(), is_corr, idx + 1))

            conn.commit()
            return {
                "status": "success",
                "message": "Thêm câu hỏi mới thành công!",
                "question_id": new_qid
            }
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@app.delete("/api/admin/questions/{question_id}")
def delete_question(question_id: int):
    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM questions WHERE id = %s", (question_id,))
            conn.commit()
            return {"status": "success", "message": "Đã xóa câu hỏi thành công!"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@app.get("/api/admin/exams/{exam_id}/submissions")
def get_exam_submissions(exam_id: int, class_id: Optional[int] = None):
    """Lấy danh sách bảng điểm của học sinh làm bài thi này."""
    conn = get_db()
    try:
        with conn.cursor() as cursor:
            query = """
                SELECT sub.id as submission_id, sub.start_time, sub.submitted_at, sub.score, sub.status,
                       u.id as student_id, u.username, u.full_name, c.name as class_name,
                       e.total_score, e.title as exam_title
                FROM exam_submissions sub
                JOIN users u ON sub.student_id = u.id
                LEFT JOIN classes c ON u.class_id = c.id
                JOIN exams e ON sub.exam_id = e.id
                WHERE sub.exam_id = %s
            """
            params = [exam_id]
            if class_id:
                query += " AND u.class_id = %s"
                params.append(class_id)
            query += " ORDER BY sub.score DESC, sub.submitted_at ASC"

            cursor.execute(query, tuple(params))
            subs = cursor.fetchall()
            return {"status": "success", "submissions": subs}
    finally:
        conn.close()


def build_student_submission_export(submission_id: int):
    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT sub.id, sub.student_id, sub.status, sub.score, sub.submitted_at,
                       sub.shuffled_data, u.full_name, u.username, c.name AS class_name,
                       e.title AS exam_title, e.total_score
                FROM exam_submissions sub
                JOIN users u ON u.id = sub.student_id
                LEFT JOIN classes c ON c.id = u.class_id
                JOIN exams e ON e.id = sub.exam_id
                WHERE sub.id = %s
                """,
                (submission_id,),
            )
            submission = cursor.fetchone()
            if not submission:
                raise HTTPException(status_code=404, detail="Không tìm thấy bài nộp!")
            if submission["status"] not in ("submitted", "graded", "timed_out"):
                raise HTTPException(status_code=409, detail="Bài thi chưa được nộp.")

            cursor.execute(
                """
                SELECT question_id, selected_option_id, text_answer, essay_file_url,
                       awarded_points
                FROM student_answers
                WHERE submission_id = %s
                """,
                (submission_id,),
            )
            answers = {
                answer["question_id"]: answer for answer in cursor.fetchall()
            }

        sections = json.loads(submission["shuffled_data"] or "[]")
        for section in sections:
            for question in section.get("questions", []):
                question["section_type"] = section["section_type"]
                answer = answers.get(question["id"], {})
                original_options = question.get("options", [])
                question["earned_points"] = answer.get("awarded_points") or 0
                question["possible_points"] = question.get("points") or 0
                question["student_answer"] = "-"
                question["answers"] = []
                question["options"] = (
                    [
                        {
                            "id": option.get("id"),
                            "label": option.get("label"),
                            "content": option.get("content", ""),
                            "is_correct": bool(option.get("is_correct")),
                            "is_selected": option.get("id") == answer.get("selected_option_id"),
                        }
                        for option in original_options
                    ]
                    if section["section_type"] != "g3"
                    else []
                )

                if section["section_type"] == "g1":
                    selected_option = next(
                        (
                            option for option in original_options
                            if option["id"] == answer.get("selected_option_id")
                        ),
                        None,
                    )
                    if selected_option:
                        question["student_answer"] = (
                            f"{selected_option.get('label', '')}. "
                            f"{selected_option.get('content', '')}"
                        )
                elif section["section_type"] == "g2":
                    text_answer = answer.get("text_answer")
                    try:
                        selected_answers = json.loads(text_answer or "{}")
                    except json.JSONDecodeError:
                        selected_answers = {}
                    question["student_tf_answers"] = selected_answers
                    question["answers"] = [
                        f"{option.get('label', '')}) {option.get('content', '')} - "
                        f"{'Đúng' if selected_answers.get(str(option['id'])) in (True, 'true') else 'Sai'}"
                        for option in original_options
                        if str(option["id"]) in selected_answers
                    ]
                else:
                    question["correct_short_answer"] = next(
                        (
                            option.get("content")
                            for option in original_options
                            if option.get("is_correct")
                        ),
                        None,
                    )
                    question["student_answer"] = (
                        answer.get("text_answer")
                        or answer.get("essay_file_url")
                        or "-"
                    )

        pdf_bytes = build_student_submission_pdf(
            submission["exam_title"],
            submission["full_name"],
            submission["username"],
            submission["class_name"],
            submission["score"],
            submission["total_score"],
            submission["submitted_at"],
            sections,
            submission["status"],
        )
        return pdf_bytes, submission
    finally:
        conn.close()


def _submission_pdf_filename(submission: dict) -> str:
    def safe_component(value: object, fallback: str) -> str:
        text = str(value or "").replace("đ", "d").replace("Đ", "D")
        text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
        text = re.sub(r"[^A-Za-z0-9._ -]+", "-", text)
        text = re.sub(r"\s+", " ", text).strip(" ._-")
        return text or fallback

    class_name = safe_component(submission.get("class_name"), "Lop")
    exam_title = safe_component(submission.get("exam_title"), "Bai kiem tra")
    username = safe_component(
        submission.get("username"),
        f"hoc-sinh-{submission.get('student_id', '')}",
    )
    random_suffix = f"{secrets.randbelow(1000):03d}"
    return f"{class_name}_{exam_title}_{username}_{random_suffix}.pdf"


def upload_student_submission(submission_id: int):
    try:
        pdf_bytes, submission = build_student_submission_export(submission_id)
        uploaded_file = upload_pdf_to_drive(
            pdf_bytes,
            _submission_pdf_filename(submission),
        )
    except (DriveConfigurationError, DriveUploadError, RuntimeError) as exc:
        return {"status": "failed", "detail": str(exc)}

    return {
        "status": "uploaded",
        "message": "Đã gửi bài nộp lên Google Drive.",
        "file": uploaded_file,
    }


def _set_submission_drive_upload_status(
    submission_id: int,
    status: str,
    detail: Optional[str] = None,
    file_id: Optional[str] = None,
    file_url: Optional[str] = None,
    attempts: Optional[int] = None,
) -> None:
    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE exam_submissions
                SET drive_upload_status = %s,
                    drive_upload_detail = %s,
                    drive_file_id = %s,
                    drive_file_url = %s,
                    drive_upload_attempts = COALESCE(%s, drive_upload_attempts)
                WHERE id = %s
                """,
                (status, detail, file_id, file_url, attempts, submission_id),
            )
        conn.commit()
    finally:
        conn.close()


def process_submission_drive_upload(submission_id: int, attempt: int = 1) -> None:
    while True:
        _set_submission_drive_upload_status(
            submission_id,
            "uploading",
            attempts=attempt,
        )
        try:
            result = upload_student_submission(submission_id)
        except Exception as exc:
            print(
                f"[DRIVE UPLOAD] Lỗi không mong đợi cho lượt nộp "
                f"{submission_id}, lần {attempt}: {exc}"
            )
            result = {"status": "failed", "detail": str(exc)}

        if result.get("status") == "uploaded":
            uploaded_file = result["file"]
            _set_submission_drive_upload_status(
                submission_id,
                "uploaded",
                file_id=uploaded_file["id"],
                file_url=uploaded_file["web_view_link"],
                attempts=attempt,
            )
            return

        detail = result.get("detail", "Không thể gửi PDF lên Google Drive.")
        if attempt >= 3:
            _set_submission_drive_upload_status(
                submission_id,
                "failed",
                detail=detail,
                attempts=attempt,
            )
            return

        _set_submission_drive_upload_status(
            submission_id,
            "uploading",
            detail=detail,
            attempts=attempt,
        )
        time.sleep(2 ** (attempt - 1))
        attempt += 1


def process_next_submission_drive_upload() -> bool:
    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT id, drive_upload_attempts
                FROM exam_submissions
                WHERE drive_upload_status = 'pending'
                ORDER BY id
                LIMIT 1
            """)
            submission = cursor.fetchone()
            if not submission:
                return False

            cursor.execute(
                """
                UPDATE exam_submissions
                SET drive_upload_status = 'uploading',
                    drive_upload_attempts = drive_upload_attempts + 1
                WHERE id = %s AND drive_upload_status = 'pending'
                """,
                (submission["id"],),
            )
            claimed = cursor.rowcount == 1
        conn.commit()
    finally:
        conn.close()

    if claimed:
        process_submission_drive_upload(
            submission["id"],
            submission["drive_upload_attempts"] + 1,
        )
    return claimed


async def submission_drive_upload_worker() -> None:
    loop = asyncio.get_running_loop()
    while True:
        try:
            processed = await loop.run_in_executor(
                None,
                process_next_submission_drive_upload,
            )
            if not processed:
                await asyncio.sleep(1)
        except Exception as exc:
            print(f"[DRIVE UPLOAD] Lỗi xử lý hàng đợi: {exc}")
            await asyncio.sleep(5)


@app.get("/api/student/submissions/{submission_id}/drive-status")
def get_submission_drive_status(submission_id: int):
    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT drive_upload_status, drive_upload_detail,
                       drive_file_id, drive_file_url
                FROM exam_submissions
                WHERE id = %s
                """,
                (submission_id,),
            )
            submission = cursor.fetchone()
            if not submission:
                raise HTTPException(status_code=404, detail="Không tìm thấy bài nộp!")
            return {
                "status": submission["drive_upload_status"] or "not_requested",
                "detail": submission["drive_upload_detail"],
                "file": (
                    {
                        "id": submission["drive_file_id"],
                        "web_view_link": submission["drive_file_url"],
                    }
                    if submission["drive_file_id"]
                    else None
                ),
            }
    finally:
        conn.close()


@app.get("/api/admin/submissions/{submission_id}")
def get_submission_detail(submission_id: int):
    """Xem chi tiết toàn bộ bài làm và câu trả lời của một học sinh."""
    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT sub.*, u.full_name, u.username, c.name as class_name, e.title as exam_title, e.duration_minutes
                FROM exam_submissions sub
                JOIN users u ON sub.student_id = u.id
                LEFT JOIN classes c ON u.class_id = c.id
                JOIN exams e ON sub.exam_id = e.id
                WHERE sub.id = %s
            """, (submission_id,))
            sub = cursor.fetchone()
            if not sub:
                raise HTTPException(status_code=404, detail="Không tìm thấy bài làm!")

            # Lấy các câu trả lời
            cursor.execute("""
                SELECT sa.*, q.content as question_content, q.points as question_points,
                       s.section_type, s.title as section_title
                FROM student_answers sa
                JOIN questions q ON sa.question_id = q.id
                JOIN exam_sections s ON q.section_id = s.id
                WHERE sa.submission_id = %s
                ORDER BY s.order_index ASC, q.order_index ASC
            """, (submission_id,))
            answers = cursor.fetchall()

            for ans in answers:
                cursor.execute("SELECT * FROM question_options WHERE question_id = %s", (ans["question_id"],))
                ans["options"] = cursor.fetchall()

            answer_by_question = {ans["question_id"]: ans for ans in answers}
            review_sections = json.loads(sub["shuffled_data"]) if sub.get("shuffled_data") else []
            if not review_sections:
                cursor.execute("""
                    SELECT id, section_type, title, points
                    FROM exam_sections
                    WHERE exam_id = %s
                    ORDER BY order_index ASC
                """, (sub["exam_id"],))
                review_sections = cursor.fetchall()
                for section in review_sections:
                    cursor.execute("""
                        SELECT id, content, points, order_index
                        FROM questions
                        WHERE section_id = %s
                        ORDER BY order_index ASC
                    """, (section["id"],))
                    section["questions"] = cursor.fetchall()
                    for index, question in enumerate(section["questions"], start=1):
                        question["number"] = index
                        cursor.execute("""
                            SELECT id, option_label AS label, content
                            FROM question_options
                            WHERE question_id = %s
                            ORDER BY order_index ASC
                        """, (question["id"],))
                        question["options"] = cursor.fetchall()

            for section in review_sections:
                for question in section.get("questions", []):
                    answer = answer_by_question.get(question["id"])
                    cursor.execute("""
                        SELECT id, is_correct, content
                        FROM question_options
                        WHERE question_id = %s
                    """, (question["id"],))
                    options_by_id = {option["id"]: option for option in cursor.fetchall()}
                    question["options"] = [
                        {
                            **option,
                            "is_correct": bool(options_by_id.get(option["id"], {}).get("is_correct")),
                            "is_selected": bool(
                                answer and answer.get("selected_option_id") == option["id"]
                            ),
                        }
                        for option in question.get("options", [])
                    ]
                    question["student_text_answer"] = answer.get("text_answer") if answer else None
                    question["awarded_points"] = (
                        float(answer["awarded_points"] or 0) if answer else 0
                    )
                    question["is_correct"] = bool(answer and answer.get("is_correct"))
                    question["student_tf_answers"] = {}
                    if section["section_type"] == "g2" and answer and answer.get("text_answer"):
                        question["student_tf_answers"] = json.loads(answer["text_answer"])
                    question["correct_short_answer"] = next(
                        (
                            option["content"]
                            for option in question["options"]
                            if option["is_correct"]
                        ),
                        None,
                    )

            sub["review_sections"] = review_sections
            sub["answers"] = answers
            return {"status": "success", "submission": sub}
    finally:
        conn.close()

# ==================== STUDENT: LÀM BÀI THI ====================
@app.get("/api/student/exams")
def get_student_exams(student_id: int):
    """Lấy danh sách bài thi kèm trạng thái mới nhất của học sinh."""
    allow_multiple_attempts = os.getenv(
        "ALLOW_MULTIPLE_EXAM_ATTEMPTS", ""
    ).strip().lower() in {"1", "true", "yes", "on"}
    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT e.*,
                       COALESCE(question_counts.section_count, 0) as section_count,
                       COALESCE(question_counts.question_count, 0) as question_count,
                       sub.id as submission_id,
                       sub.status as student_status,
                       sub.score as student_score,
                       sub.submitted_at as student_submitted_at
                FROM users student
                JOIN exams e ON e.class_id IS NULL OR e.class_id = student.class_id
                LEFT JOIN (
                    SELECT s.exam_id,
                           COUNT(DISTINCT s.id) as section_count,
                           COUNT(DISTINCT q.id) as question_count
                    FROM exam_sections s
                    LEFT JOIN questions q ON q.section_id = s.id
                    GROUP BY s.exam_id
                ) question_counts ON question_counts.exam_id = e.id
                LEFT JOIN exam_submissions sub ON sub.id = (
                    SELECT MAX(latest.id)
                    FROM exam_submissions latest
                    WHERE latest.exam_id = e.id AND latest.student_id = student.id
                )
                WHERE student.id = %s AND student.role = 'student'
                  AND student.is_active = 1 AND e.is_published = 1
                ORDER BY e.id DESC
            """, (student_id,))
            exams = cursor.fetchall()
            return {
                "status": "success",
                "exams": exams,
                "allow_multiple_attempts": allow_multiple_attempts,
            }
    finally:
        conn.close()

@app.get("/api/student/submissions/{submission_id}/review")
def get_student_submission_review(submission_id: int, student_id: int):
    """Return a student's submitted questions without exposing their answers."""
    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT sub.id, sub.student_id, sub.status, sub.score,
                       sub.shuffled_data, e.title as exam_title, e.total_score
                FROM exam_submissions sub
                JOIN exams e ON e.id = sub.exam_id
                WHERE sub.id = %s AND sub.student_id = %s
            """, (submission_id, student_id))
            submission = cursor.fetchone()
            if not submission:
                raise HTTPException(status_code=404, detail="Không tìm thấy bài làm!")
            if submission["status"] not in ["submitted", "graded", "timed_out"]:
                raise HTTPException(status_code=409, detail="Bài thi chưa được nộp.")

            sections = json.loads(submission["shuffled_data"] or "[]")
            cursor.execute("""
                SELECT question_id, is_correct, awarded_points
                FROM student_answers
                WHERE submission_id = %s
            """, (submission_id,))
            question_results = {
                answer["question_id"]: answer for answer in cursor.fetchall()
            }

            review_sections = []
            for section in sections:
                review_questions = []
                for question in section.get("questions", []):
                    result = question_results.get(question["id"])
                    review_questions.append({
                        "number": question["number"],
                        "content": question["content"],
                        "options": (
                            [
                                {"label": option.get("label"), "content": option["content"]}
                                for option in question.get("options", [])
                            ]
                            if section["section_type"] != "g3"
                            else []
                        ),
                        "earned_points": (
                            float(result["awarded_points"] or 0)
                            if result
                            else 0.0
                        ),
                        "possible_points": float(question.get("points") or 0),
                    })
                review_sections.append({
                    "section_type": section["section_type"],
                    "title": section["title"],
                    "questions": review_questions,
                })

            return {
                "status": "success",
                "exam_title": submission["exam_title"],
                "score": submission["score"],
                "total_score": submission["total_score"],
                "sections": review_sections,
            }
    finally:
        conn.close()

@app.post("/api/student/exams/{exam_id}/start")
def start_exam(exam_id: int, student_id: int = Form(...)):
    """
    Học sinh bắt đầu làm bài.
    Sinh mã đề riêng biệt theo chuẩn GDPT 2018:
    - <#g1>: Hoán vị cả câu hỏi và các phương án
    - <#g2>: Cố định thứ tự câu hỏi, hoán vị các ý a, b, c, d
    - <#g3>: Hoán vị câu hỏi, học sinh nhập đáp án ngắn
    - <#g4>: Giữ nguyên thứ tự câu hỏi và tự luận
    """
    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT class_id FROM users WHERE id = %s AND role = 'student' AND is_active = 1",
                (student_id,),
            )
            student = cursor.fetchone()
            if not student:
                raise HTTPException(status_code=403, detail="Tài khoản học sinh không hợp lệ.")

            cursor.execute("SELECT class_id FROM exams WHERE id = %s", (exam_id,))
            exam_access = cursor.fetchone()
            if not exam_access:
                raise HTTPException(status_code=404, detail="Không tìm thấy bài thi!")
            if exam_access["class_id"] is not None and exam_access["class_id"] != student["class_id"]:
                raise HTTPException(status_code=403, detail="Bài thi này không dành cho lớp của bạn.")

            allow_multiple_attempts = os.getenv(
                "ALLOW_MULTIPLE_EXAM_ATTEMPTS", ""
            ).strip().lower() in {"1", "true", "yes", "on"}

            # 1. Kiểm tra xem học sinh đã có bài làm chưa
            cursor.execute("""
                SELECT * FROM exam_submissions 
                WHERE exam_id = %s AND student_id = %s 
                ORDER BY id DESC LIMIT 1
            """, (exam_id, student_id))
            existing_sub = cursor.fetchone()

            if (
                not allow_multiple_attempts
                and existing_sub
                and existing_sub["status"] in ["submitted", "graded", "timed_out"]
            ):
                return {
                    "status": "already_submitted",
                    "message": "Bạn đã làm bài kiểm tra này rồi!",
                    "submission_id": existing_sub["id"],
                    "score": existing_sub["score"]
                }

            # Lấy thông tin bài thi
            cursor.execute("SELECT * FROM exams WHERE id = %s", (exam_id,))
            exam = cursor.fetchone()
            if not exam:
                raise HTTPException(status_code=404, detail="Không tìm thấy bài thi!")

            # Nếu đang làm dở (in_progress) -> Khôi phục đề đã sinh và các câu đã chọn
            if existing_sub and existing_sub["status"] == "in_progress":
                shuffled_data = json.loads(existing_sub["shuffled_data"])
                cursor.execute(
                    "SELECT id, section_type FROM exam_sections WHERE exam_id = %s",
                    (exam_id,),
                )
                section_types_by_id = {
                    section["id"]: section["section_type"]
                    for section in cursor.fetchall()
                }
                section_types_changed = False
                for section in shuffled_data:
                    section_type = section_types_by_id.get(section["id"])
                    if not section_type or section.get("section_type") == section_type:
                        continue

                    section["section_type"] = section_type
                    section_types_changed = True
                    labels = (
                        ["a", "b", "c", "d", "e"]
                        if section_type in ["g2", "g4"]
                        else ["A", "B", "C", "D", "E", "F"]
                    )
                    for question in section.get("questions", []):
                        for index, option in enumerate(question.get("options", [])):
                            if index < len(labels):
                                option["label"] = labels[index]

                if section_types_changed:
                    cursor.execute(
                        "UPDATE exam_submissions SET shuffled_data = %s WHERE id = %s",
                        (json.dumps(shuffled_data, ensure_ascii=False), existing_sub["id"]),
                    )
                    conn.commit()

                # Lấy các đáp án đã lưu trước đó
                cursor.execute("""
                    SELECT question_id, selected_option_id, text_answer 
                    FROM student_answers WHERE submission_id = %s
                """, (existing_sub["id"],))
                saved_answers = cursor.fetchall()

                return {
                    "status": "resumed",
                    "submission_id": existing_sub["id"],
                    "exam_title": exam["title"],
                    "duration_minutes": exam["duration_minutes"],
                    "start_time": str(existing_sub["start_time"]),
                    "shuffled_exam": shuffled_data,
                    "saved_answers": saved_answers
                }

            # 2. Sinh đề mới với thuật toán xáo trộn theo từng phần
            cursor.execute("SELECT * FROM exam_sections WHERE exam_id = %s ORDER BY order_index ASC", (exam_id,))
            sections = cursor.fetchall()

            shuffled_sections = []
            flat_question_index = 1

            for sec in sections:
                section_type = sec["section_type"]
                shuffle_questions = sec["shuffle_questions"]
                shuffle_options = sec["shuffle_options"]

                cursor.execute("SELECT * FROM questions WHERE section_id = %s ORDER BY order_index ASC", (sec['id'],))
                questions = cursor.fetchall()

                # Quy tắc trộn câu hỏi
                if shuffle_questions == 1:
                    random.shuffle(questions)

                shuffled_questions = []
                for q in questions:
                    cursor.execute("SELECT id, option_label, content, is_correct, order_index FROM question_options WHERE question_id = %s ORDER BY order_index ASC", (q['id'],))
                    options = cursor.fetchall()

                    # Quy tắc trộn phương án
                    if shuffle_options == 1 and len(options) > 1:
                        random.shuffle(options)

                    # Gán nhãn A, B, C, D (hoặc a, b, c, d) hiển thị tuần tự cho học sinh
                    display_labels = ['a', 'b', 'c', 'd', 'e'] if section_type in ['g2', 'g4'] else ['A', 'B', 'C', 'D', 'E', 'F']
                    safe_options = []
                    for idx, opt in enumerate(options):
                        lbl = display_labels[idx] if idx < len(display_labels) else opt["option_label"]
                        # LƯU Ý BẢO MẬT: KHÔNG gửi cờ is_correct về máy học sinh để tránh gian lận
                        safe_options.append({
                            "id": opt["id"],
                            "label": lbl,
                            "content": opt["content"]
                        })

                    shuffled_questions.append({
                        "id": q["id"],
                        "number": flat_question_index,
                        "content": q["content"],
                        "points": float(q["points"]),
                        "options": safe_options
                    })
                    flat_question_index += 1

                shuffled_sections.append({
                    "id": sec["id"],
                    "section_type": section_type,
                    "title": sec["title"],
                    "points": float(sec["points"]),
                    "questions": shuffled_questions
                })

            now = datetime.datetime.now()
            shuffled_json = json.dumps(shuffled_sections, ensure_ascii=False)

            # 3. Tạo lượt thi trong bảng exam_submissions
            cursor.execute("""
                INSERT INTO exam_submissions (exam_id, student_id, start_time, status, shuffled_data)
                VALUES (%s, %s, %s, 'in_progress', %s)
            """, (exam_id, student_id, now, shuffled_json))
            submission_id = cursor.lastrowid
            conn.commit()

            return {
                "status": "started",
                "submission_id": submission_id,
                "exam_title": exam["title"],
                "duration_minutes": exam["duration_minutes"],
                "start_time": str(now),
                "shuffled_exam": shuffled_sections,
                "saved_answers": []
            }
    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@app.post("/api/student/submissions/{submission_id}/save-answer")
def save_student_answer(submission_id: int, req: SaveAnswerRequest):
    """
    Tự động lưu câu trả lời ngay khi học sinh chọn hoặc nhập đáp án (tránh mất bài).
    """
    conn = get_db()
    try:
        with conn.cursor() as cursor:
            # Kiểm tra trạng thái submission
            cursor.execute("SELECT status FROM exam_submissions WHERE id = %s", (submission_id,))
            sub = cursor.fetchone()
            if not sub or sub["status"] != "in_progress":
                return {"status": "ignored", "message": "Bài thi đã nộp hoặc không khả dụng."}

            # Nếu là câu Đúng/Sai dạng nhiều ý: serialize tf_answers vào text_answer
            text_ans = req.text_answer
            if req.tf_answers:
                text_ans = json.dumps(req.tf_answers)

            cursor.execute("""
                INSERT INTO student_answers (submission_id, question_id, selected_option_id, text_answer)
                VALUES (%s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE 
                    selected_option_id = VALUES(selected_option_id),
                    text_answer = VALUES(text_answer)
            """, (submission_id, req.question_id, req.selected_option_id, text_ans))
            conn.commit()
            return {"status": "success", "message": "Đã lưu câu trả lời!"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@app.post("/api/student/submissions/{submission_id}/submit")
def submit_exam(submission_id: int):
    """
    Nộp bài thi & Hệ thống tự động chấm điểm theo Quy chế GDPT 2018:
    - Phần I (g1): Chọn 1 đáp án. Đúng nhận trọn điểm câu.
    - Phần II (g2): Đúng/Sai (4 ý):
      + Đúng 1 ý: 10% điểm câu
      + Đúng 2 ý: 25% điểm câu
      + Đúng 3 ý: 50% điểm câu
      + Đúng 4 ý: 100% điểm câu
    - Phần III (g3): Trả lời ngắn: So khớp chuỗi đáp án (chuẩn hóa chữ thường, xóa khoảng trắng thừa).
    - Phần IV (g4): Tự luận (chờ giáo viên chấm).
    """
    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM exam_submissions WHERE id = %s", (submission_id,))
            sub = cursor.fetchone()
            if not sub:
                raise HTTPException(status_code=404, detail="Không tìm thấy bài nộp!")
            if sub["status"] in ["submitted", "graded"]:
                cursor.execute(
                    """
                    SELECT COUNT(DISTINCT q.id) AS total_questions,
                           COUNT(DISTINCT CASE WHEN sa.is_correct = 1 THEN q.id END)
                               AS correct_questions
                    FROM exam_sections s
                    JOIN questions q ON q.section_id = s.id
                    LEFT JOIN student_answers sa
                        ON sa.question_id = q.id AND sa.submission_id = %s
                    WHERE s.exam_id = %s
                    """,
                    (submission_id, sub["exam_id"]),
                )
                result_counts = cursor.fetchone() or {}
                return {
                    "status": "already_submitted",
                    "message": "Bài thi đã được nộp trước đó; không gửi lại PDF.",
                    "score": sub["score"],
                    "correct_questions": result_counts.get("correct_questions", 0),
                    "total_questions": result_counts.get("total_questions", 0),
                    "drive_upload": (
                        {
                            "status": sub["drive_upload_status"],
                            "detail": sub["drive_upload_detail"],
                            "file": {
                                "id": sub["drive_file_id"],
                                "web_view_link": sub["drive_file_url"],
                            } if sub["drive_file_id"] else None,
                        }
                        if sub.get("drive_upload_status")
                        else None
                    ),
                }

            # Lấy tất cả câu hỏi của đề thi cùng thông tin section
            cursor.execute("""
                SELECT q.id as question_id, q.points as question_points,
                       s.section_type, s.title as section_title
                FROM questions q
                JOIN exam_sections s ON q.section_id = s.id
                WHERE s.exam_id = %s
            """, (sub["exam_id"],))
            questions = cursor.fetchall()

            # Lấy tất cả câu trả lời của học sinh
            cursor.execute("SELECT * FROM student_answers WHERE submission_id = %s", (submission_id,))
            student_answers_map = {a["question_id"]: a for a in cursor.fetchall()}
            question_ids = [question["question_id"] for question in questions]
            options_by_question = {}
            if question_ids:
                placeholders = ", ".join(["%s"] * len(question_ids))
                cursor.execute(
                    f"""
                    SELECT question_id, id, is_correct, content
                    FROM question_options
                    WHERE question_id IN ({placeholders})
                    """,
                    tuple(question_ids),
                )
                for option in cursor.fetchall():
                    options_by_question.setdefault(option["question_id"], []).append(option)

            total_earned_score = 0.0
            correct_questions_count = 0
            answer_scores = []

            for q in questions:
                qid = q["question_id"]
                q_pts = float(q["question_points"])
                sec_type = q["section_type"]
                stu_ans = student_answers_map.get(qid)

                awarded = 0.0
                is_correct = 0

                options = options_by_question.get(qid, [])

                # --- 1. CHẤM PHẦN I (g1): Trắc nghiệm 1 đáp án ---
                if sec_type == 'g1':
                    correct_opt = next((o for o in options if o["is_correct"] == 1), None)
                    if stu_ans and stu_ans["selected_option_id"] and correct_opt:
                        if stu_ans["selected_option_id"] == correct_opt["id"]:
                            awarded = q_pts
                            is_correct = 1
                            correct_questions_count += 1

                # --- 2. CHẤM PHẦN II (g2): Trắc nghiệm Đúng / Sai (Quy chế GDPT 2018) ---
                elif sec_type == 'g2':
                    # Mỗi option tương ứng một ý (a, b, c, d). is_correct=1 nghĩa là ý đó ĐÚNG, 0 là SAI.
                    if stu_ans and stu_ans["text_answer"]:
                        try:
                            # text_answer chứa dict dạng: { "opt_id": "true" | "false" }
                            tf_map = json.loads(stu_ans["text_answer"])
                            matched_sub_count = 0
                            total_subs = len(options)

                            for opt in options:
                                opt_id_str = str(opt["id"])
                                stu_choice = tf_map.get(opt_id_str) # "true" hoặc "false"
                                actual_is_true = (opt["is_correct"] == 1)

                                if stu_choice is not None:
                                    is_stu_true = (stu_choice.lower() == 'true')
                                    if is_stu_true == actual_is_true:
                                        matched_sub_count += 1

                            # Thang điểm chuẩn GDPT 2018
                            if total_subs == 4:
                                if matched_sub_count == 1:
                                    awarded = round(q_pts * 0.1, 2)
                                elif matched_sub_count == 2:
                                    awarded = round(q_pts * 0.25, 2)
                                elif matched_sub_count == 3:
                                    awarded = round(q_pts * 0.5, 2)
                                elif matched_sub_count == 4:
                                    awarded = q_pts
                                    is_correct = 1
                                    correct_questions_count += 1
                            else:
                                # Tỷ lệ thuận nếu số ý khác 4
                                awarded = round((matched_sub_count / total_subs) * q_pts, 2) if total_subs > 0 else 0
                                if matched_sub_count == total_subs and total_subs > 0:
                                    is_correct = 1
                                    correct_questions_count += 1
                        except:
                            awarded = 0.0

                # --- 3. CHẤM PHẦN III (g3): Trả lời ngắn ---
                elif sec_type == 'g3':
                    # Chuỗi đáp án chuẩn
                    correct_opt = next((o for o in options if o["is_correct"] == 1), None)
                    if stu_ans and stu_ans["text_answer"] and correct_opt:
                        stu_txt = stu_ans["text_answer"].strip().lower()
                        corr_txt = correct_opt["content"].strip().lower()
                        # Xóa khoảng trắng thừa
                        stu_txt = re.sub(r'\s+', '', stu_txt)
                        corr_txt = re.sub(r'\s+', '', corr_txt)
                        if stu_txt == corr_txt:
                            awarded = q_pts
                            is_correct = 1
                            correct_questions_count += 1

                # --- 4. PHẦN IV (g4): Tự luận ---
                elif sec_type == 'g4':
                    awarded = 0.0 # Chờ giáo viên chấm thủ công

                total_earned_score += awarded

                # Cập nhật điểm cho câu này trong bảng student_answers
                if stu_ans:
                    answer_scores.append((is_correct, awarded, stu_ans["id"]))

            if answer_scores:
                cursor.executemany(
                    """
                    UPDATE student_answers
                    SET is_correct = %s, awarded_points = %s
                    WHERE id = %s
                    """,
                    answer_scores,
                )

            # Cập nhật trạng thái bài nộp
            total_earned_score = round(total_earned_score, 2)
            now = datetime.datetime.now()
            cursor.execute("""
                UPDATE exam_submissions
                SET status = 'graded', score = %s, submitted_at = %s,
                    drive_upload_status = 'pending',
                    drive_upload_detail = NULL,
                    drive_file_id = NULL,
                    drive_file_url = NULL,
                    drive_upload_attempts = 0
                WHERE id = %s
            """, (total_earned_score, now, submission_id))

            conn.commit()

            return {
                "status": "success",
                "message": "Nộp bài thành công!",
                "score": total_earned_score,
                "correct_questions": correct_questions_count,
                "total_questions": len(questions),
                "drive_upload": {"status": "pending"},
            }
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

# ==================== FRONTEND ROUTES ====================
@app.get("/")
def serve_index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))

@app.get("/admin")
def serve_admin():
    return FileResponse(os.path.join(STATIC_DIR, "admin.html"))

@app.get("/exam")
def serve_exam():
    return FileResponse(os.path.join(STATIC_DIR, "exam.html"))

@app.get("/service-worker.js")
def serve_service_worker():
    return FileResponse(
        os.path.join(STATIC_DIR, "service-worker.js"),
        media_type="application/javascript",
        headers={"Cache-Control": "no-cache", "Service-Worker-Allowed": "/"},
    )