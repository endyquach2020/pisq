# PisQ - Hệ Thống Thi Trắc Nghiệm Trực Tuyến Chuẩn GDPT 2018

Hệ thống thi trắc nghiệm trực tuyến linh hoạt theo cấu trúc 4 phần đề thi của Bộ Giáo dục & Đào tạo (chuẩn GDPT 2018):
- **Phần I (`<#g1>`):** Câu hỏi trắc nghiệm nhiều lựa chọn (hoán vị câu hỏi và phương án A, B, C, D).
- **Phần II (`<#g2>`):** Trắc nghiệm lựa chọn Đúng / Sai (cố định câu hỏi, hoán vị các ý a, b, c, d, chấm điểm chuẩn quy chế Bộ GD&ĐT).
- **Phần III (`<#g3>`):** Câu hỏi trắc nghiệm trả lời ngắn (hoán vị câu hỏi, học sinh nhập đáp án).
- **Phần IV (`<#g4>`):** Tự luận / Listening (giữ nguyên thứ tự).

---

## 🛠️ Công nghệ sử dụng
- **Backend:** Python (FastAPI, Uvicorn, Python-Docx, PyMySQL, OpenPyXL)
- **Frontend:** HTML5, Vanilla CSS (Dark Mode), JavaScript, KaTeX (render công thức toán học)
- **Cơ sở dữ liệu:** MySQL (tương thích MariaDB / MySQL 8.x)

---

## 🚀 Hướng dẫn chạy trên Local (XAMPP)

1. Mở XAMPP Control Panel, bật **Apache** và **MySQL**.
2. Tạo database tên `pisq` trên phpMyAdmin (`http://localhost/phpmyadmin/`).
3. Import file `database_schema.sql` vào database `pisq`.
4. Cài đặt các thư viện cần thiết:
   ```bash
   pip install -r requirements.txt
   ```
5. Khởi chạy máy chủ:
   - Nháy đúp vào file `run_server.bat`  
   - Hoặc gõ lệnh:
     ```bash
     python -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
     ```
6. Mở trình duyệt vào:
   - Qua cổng XAMPP: `http://localhost/pisq/` (tự động chuyển hướng)
   - Hoặc trực tiếp: `http://localhost:8000/`

---

## ☁️ Hướng dẫn đẩy lên GitHub & Triển khai Hosting / Cloud

### 1. Đẩy mã nguồn lên GitHub:
```bash
git init
git add .
git commit -m "Initial commit PisQ Exam System"
git branch -M main
git remote add origin https://github.com/TÊN_TÀI_KHOẢN/pisq.git
git push -u origin main
```
*(Lưu ý: File `.gitignore` đã được cấu hình tự động loại bỏ các thư mục nặng như `venv`, `__pycache__` và file tạm).*

### 2. Kết nối CSDL MySQL bản mua (Cloud Database):
Khi triển khai lên hosting (VPS, Render, Railway, cPanel...), bạn chỉ cần đặt các biến môi trường (Environment Variables) hoặc tạo file `.env`:
```env
DB_HOST=dia-chi-host-mysql-mua.com
DB_PORT=3306
DB_USER=ten_user_mysql
DB_PASSWORD=mat_khau_mysql
DB_NAME=ten_database_cua_ban
```
Hệ thống sẽ tự động nhận diện và kết nối trực tiếp đến database MySQL của bạn mà không cần sửa bất kỳ dòng code nào.

---

## 👤 Tài khoản thử nghiệm mặc định

- **Học sinh:**
  - Tên đăng nhập: `nguyenvanan`
  - Mật khẩu: `123456`
- **Quản trị viên / Giáo viên:**
  - Tên đăng nhập: `admin`
  - Mật khẩu: `admin123`
  - URL Quản trị: `http://localhost:8000/admin`
