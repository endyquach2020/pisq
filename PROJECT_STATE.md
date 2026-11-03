# TRẠNG THÁI DỰ ÁN PISQ - HỆ THỐNG THI TRẮC NGHIỆM TRỰC TUYẾN

> **Thời điểm cập nhật:** 03/11/2026  
> **Trạng thái:** Đã hoàn thành toàn bộ Bước 1, Bước 2, Bước 3, Bước 4. Hệ thống đang chạy trực tiếp trên `http://localhost:8000`.

---

## 1. Tóm tắt yêu cầu dự án
Hệ thống thi trắc nghiệm trực tuyến chuẩn định dạng GDPT 2018 (tương tự Azota / YoungMix):
1. **Phân nhóm câu hỏi & Cơ chế trộn đề:**
   - `<#g1>`: Phần I. Trắc nghiệm nhiều phương án (Hoán vị cả câu hỏi và các đáp án A, B, C, D).
   - `<#g2>`: Phần II. Đúng / Sai (Cố định thứ tự câu hỏi, hoán vị các ý a, b, c, d). Chấm theo quy chế GDPT 2018 (1 ý: 10%, 2 ý: 25%, 3 ý: 50%, 4 ý: 100%).
   - `<#g3>`: Phần III. Trả lời ngắn (Hoán vị thứ tự câu hỏi, học sinh nhập đáp án ngắn).
   - `<#g4>`: Phần IV. Tự luận / Listening tiếng Anh (Không trộn, giữ nguyên thứ tự).
   - Cấu trúc linh hoạt (đề có phần nào tính phần đó, giáo viên có thể cấu hình điểm/chia điểm từng phần).
2. **Quy tắc bóc tách file Word (.docx):**
   - Hỗ trợ công thức Toán học (LaTeX/OMML) hiển thị KaTeX sắc nét và hình ảnh nhúng (Inline with text).
   - Câu hỏi bắt đầu bằng "Câu X" hoặc "Question X".
   - Đáp án bắt đầu bằng A., B., C., D. (hoặc a, b, c, d).
   - Đáp án đúng được nhận diện bằng gạch chân (Underline).
3. **Chức năng Quản trị (Admin/Giáo viên):**
   - Thêm tài khoản học sinh theo khối, theo lớp (thủ công hoặc import từ file Excel .xlsx).
   - Upload & quản lý đề thi, chia điểm cho từng phần, cài đặt thời gian thi (thời lượng, mở/đóng ca thi).
   - Xem bảng điểm học sinh theo lớp, thống kê kết quả và xem chi tiết bài làm.
4. **Giao diện Học sinh làm bài:**
   - Giao diện Dark Mode chuẩn 100% theo mockup: cột câu hỏi bên trái, sơ đồ ma trận câu hỏi bên phải, đồng hồ đếm ngược, tự động lưu bài theo thời gian thực (auto-save).

---

## 2. Những việc đã hoàn thành
- [x] **Cơ sở dữ liệu MySQL:**
  - Kết nối hoàn hảo với MySQL XAMPP local trên database `pisq`.
  - Khởi tạo tài khoản quản trị mặc định: `admin` / `admin123`.
  - Khởi tạo học sinh mẫu khớp ảnh mockup: `nguyenvanan` / `123456` (Nguyễn Văn An, Lớp 12A1).
- [x] **Module bóc tách Word (.docx) & Công thức Toán (`docx_parser.py`):**
  - Chuyển đổi toàn diện công thức Office Math (OMML) sang LaTeX KaTeX (`$formula$`).
  - Trích xuất ảnh Inline With Text và lưu vào `static/uploads/`.
  - Tự động nhận diện thẻ nhóm `<#g1>`, `<#g2>`, `<#g3>`, `<#g4>` và gạch chân (underline) đáp án đúng.
- [x] **Backend & API (`main.py`):**
  - API xác thực/đăng nhập phân quyền Học sinh và Giáo viên (`/api/auth/login`).
  - API Quản lý lớp học & Học sinh (`/api/admin/classes`, `/api/admin/students`, `/api/admin/students/import-excel`).
  - API Nạp đề thi Word (`/api/admin/exams/import-docx`).
  - API Cấu hình đề & Chia điểm từng phần (`/api/admin/exams/{id}/config`).
  - API Sinh đề ngẫu nhiên theo chuẩn GDPT 2018 (`/api/student/exams/{id}/start`).
  - API Auto-save câu trả lời (`/api/student/submissions/{id}/save-answer`).
  - API Tự động chấm điểm chuẩn quy chế Bộ GD&ĐT (`/api/student/submissions/{id}/submit`).
  - API Bảng điểm & thống kê lớp (`/api/admin/exams/{id}/submissions`).
- [x] **Giao diện người dùng (`static/`):**
  - `index.html`: Cổng đăng nhập phân quyền & danh sách bài thi cho học sinh.
  - `exam.html`: Phòng thi trực tuyến Dark Mode cực đẹp, tích hợp KaTeX, đồng hồ đếm ngược và ma trận câu hỏi.
  - `admin.html`: Bảng điều khiển quản trị viên đầy đủ 3 phân hệ: Đề thi, Lớp học & Excel, Bảng điểm & Thống kê.
  - `css/style.css`: Giao diện Dark Mode tinh tế, responsive, hiệu ứng mượt mà.

---

## 3. Cách truy cập & kiểm tra hệ thống
- **URL chính:** `http://localhost:8000/` (hoặc `http://127.0.0.1:8000/`)
- **Tài khoản Học sinh:**
  - Tên đăng nhập: `nguyenvanan`
  - Mật khẩu: `123456`
- **Tài khoản Quản trị / Giáo viên:**
  - Tên đăng nhập: `admin`
  - Mật khẩu: `admin123`
  - URL Quản trị: `http://localhost:8000/admin`
