# PisQ - Hệ Thống Thi Trắc Nghiệm Trực Tuyến Chuẩn GDPT 2018

Hệ thống thi trắc nghiệm trực tuyến linh hoạt theo cấu trúc 4 phần đề thi của Bộ Giáo dục & Đào tạo (chuẩn GDPT 2018):
- **Phần I (`<#g1>`):** Câu hỏi trắc nghiệm nhiều lựa chọn (hoán vị câu hỏi và phương án A, B, C, D).
- **Phần II (`<#g2>`):** Trắc nghiệm lựa chọn Đúng / Sai (cố định câu hỏi, hoán vị các ý a, b, c, d, chấm điểm chuẩn quy chế Bộ GD&ĐT).
- **Phần III (`<#g3>`):** Câu hỏi trắc nghiệm trả lời ngắn (hoán vị câu hỏi, học sinh nhập đáp án).
- **Phần IV (`<#g4>`):** Tự luận / Listening (giữ nguyên thứ tự).

### Hướng dẫn soạn câu hỏi trong file Word
- Lưu đề ở định dạng `.docx`. Mỗi phần cần có thẻ `<#g1>`, `<#g2>`, `<#g3>` hoặc `<#g4>` trước câu hỏi. Thẻ quyết định loại câu; tên phần và tiêu đề chỉ để hiển thị.
- `<#g1>`: câu hỏi nhiều lựa chọn; đáp án nằm riêng từng dòng và bắt đầu bằng `A.`, `B.`, `C.`, `D.`. Gạch chân đáp án đúng. Hệ thống có thể hoán vị câu hỏi và đáp án.
- `<#g2>`: câu đúng/sai có các ý `a)`, `b)`, `c)`, `d)`; gạch chân ý đúng, ý không gạch chân được hiểu là sai. Hệ thống giữ thứ tự câu hỏi và có thể hoán vị các ý.
- `<#g3>`: câu trả lời ngắn; nhập đáp án chuẩn ở dòng riêng với tiền tố bắt buộc `DA.` hoặc `DA:`, ví dụ `DA. 12` hoặc `DA: 12`. Hệ thống có thể hoán vị câu hỏi.
- `<#g4>`: câu tự luận; các ý nhỏ bắt đầu bằng `a)`, `b)`, `c)`, `d)`. Hệ thống giữ nguyên thứ tự, học sinh trả lời trong khung nhập bài làm.
- Câu hỏi bắt đầu bằng `Câu 1.`, `Câu 2.`, ... hoặc `Question 1.`, `Question 2.`, ...; cần nhấn Enter để tách dòng và nên để mỗi đáp án/ý nhỏ trên một dòng riêng.
- Đề có thể thiếu một số phần. Công thức toán và hình ảnh được hỗ trợ; với hình ảnh trong Word, chọn chế độ `In Line with Text` để ảnh đi cùng dòng nội dung khi hoán vị.
- Hệ thống có trang đăng nhập dành cho học sinh và trang quản trị riêng. Học sinh xem các bài thi được mở cho lớp của mình.

### Khôi phục bài thi khi mất mạng hoặc mất điện
- Sau khi mở bài thi khi đang có mạng, đề và câu trả lời được lưu trên thiết bị đang dùng.
- Nếu mất mạng hoặc trình duyệt/tắt máy đột ngột, mở lại cùng bài thi bằng cùng trình duyệt và tài khoản để tiếp tục; câu trả lời chưa đồng bộ sẽ tự gửi lên máy chủ khi có mạng.
- Bộ đếm thời gian vẫn tính theo thời lượng đề thi, không tạm dừng khi mất mạng hoặc tắt máy. Cần kết nối mạng để nộp bài.

### Phân quyền bài thi theo lớp
- Khi nhập đề Word, quản trị viên có thể chọn một lớp hoặc chọn **Tất cả các lớp**. Đề chọn một lớp chỉ dành cho học sinh đang hoạt động thuộc lớp đó; đề chọn tất cả lớp dành cho mọi lớp.
- Dropdown lớp ở khu vực nạp đề cũng lọc danh sách đề bên dưới. Chọn **Tất cả các lớp** hoặc chưa chọn lớp để xem toàn bộ đề; khi lọc một lớp, các đề dành cho lớp đó và đề áp dụng cho tất cả lớp đều được hiển thị.
- Cơ sở dữ liệu cũ được bổ sung cột lớp khi ứng dụng khởi động. Các đề đã tồn tại trước khi cập nhật vẫn áp dụng cho mọi lớp.

### Bật thi lại khi kiểm thử
- Mặc định, mỗi học sinh chỉ nộp một lượt cho mỗi bài thi. Để tạm cho phép thi lại trên máy Windows local, đặt biến `ALLOW_MULTIPLE_EXAM_ATTEMPTS` thành `true`, rồi khởi động lại máy chủ. Học sinh sẽ thấy nút **Làm lại bài**; mỗi lần làm lại tạo một lượt nộp mới và vẫn giữ lịch sử các lượt trước.
- Tắt lại sau khi kiểm thử bằng cách xóa biến người dùng `ALLOW_MULTIPLE_EXAM_ATTEMPTS` hoặc đặt thành `false`, rồi khởi động lại máy chủ.

---

## 🛠️ Công nghệ sử dụng
- **Backend:** Python (FastAPI, Uvicorn, Python-Docx, PyMySQL, OpenPyXL)
- **Frontend:** HTML5, Vanilla CSS (Dark Mode), JavaScript, MathJax SVG (render công thức LaTeX sắc nét)
- **Cơ sở dữ liệu:** MySQL (tương thích MariaDB / MySQL 8.x)
- **Công thức Word:** Công thức OMML chuyển sang LaTeX; MathType OLE được MathType cho Word chuyển sang LaTeX để MathJax render dạng vector sắc nét. Máy chạy ứng dụng cần Windows, PowerShell, Microsoft Word và MathType.
- **Đề đã nhập trước đó:** cần nhập lại file `.docx` để thay ảnh xem trước cũ bằng ảnh do Microsoft Word kết xuất.

---

## 🚀 Hướng dẫn chạy trên Local (XAMPP)

1. Mở XAMPP Control Panel, bật **Apache** và **MySQL**.
2. Tạo database tên `pisq` trên phpMyAdmin (`http://localhost/phpmyadmin/`).
3. Import file `database_schema.sql` vào database `pisq`.
4. Cài đặt các thư viện cần thiết:
   ```bash
   python -m venv venv
   venv\Scripts\python.exe -m pip install -r requirements.txt
   ```
   *(Chỉ tạo `venv` ở lần cài đặt đầu tiên. Nếu đã có thư mục này, bỏ qua lệnh tạo.)*
5. Khởi chạy máy chủ:
   - Nháy đúp vào file `run_server.bat`. File sẽ tự khởi động XAMPP, chạy máy chủ FastAPI và mở trang quản trị khi máy chủ sẵn sàng.
   - Hoặc gõ lệnh:
     ```bash
     venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 3000 --reload
     ```
6. Mở trình duyệt vào:
      - Trang quản trị: `http://localhost:3000/admin` (được mở tự động khi chạy `run_server.bat`)
   - Qua cổng XAMPP: `http://localhost/pisq/` (tự động chuyển hướng)
      - Hoặc trực tiếp: `http://localhost:3000/`

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

### Chạy thử online trên Render
- Tạo một MySQL database **dùng riêng để thử nghiệm**, cho phép kết nối từ Render, rồi import `database_schema.sql` vào database trống. File schema có lệnh xóa và tạo lại các bảng, không import vào database đang có dữ liệu cần giữ.
- Đẩy mã nguồn lên GitHub, vào Render chọn tạo Blueprint từ repository này; Render sẽ đọc cấu hình trong `render.yaml`.
- Khi Render hỏi các biến `DB_HOST`, `DB_USER`, `DB_PASSWORD`, `DB_NAME` và `ADMIN_DEFAULT_PASSWORD`, nhập thông tin kết nối MySQL và đặt mật khẩu admin mạnh, riêng. Không đưa mật khẩu/token vào GitHub hoặc gửi trong chat. `DB_PORT` mặc định là `3306`.
- Khi khởi động lần đầu, ứng dụng tạo tài khoản `admin` bằng `ADMIN_DEFAULT_PASSWORD`. Ở môi trường production, máy chủ sẽ không tạo mật khẩu `admin123` mặc định.
- Gói Render miễn phí có thể dừng khi không hoạt động; các file đề và ảnh tải lên trong `static/uploads` không được lưu bền qua lần triển khai/khởi động lại. Chỉ dùng để kiểm thử; muốn sử dụng lâu dài cần lưu file trên persistent disk hoặc dịch vụ lưu trữ ngoài.

### Tự động lưu phiếu nộp bài PDF lên Google Drive qua Apps Script
- Khi học sinh bấm **Nộp bài**, kết quả được xác nhận ngay; hệ thống tạo PDF và gửi tới Apps Script để lưu vào Drive ở nền. Trạng thái gửi được lưu trong MySQL, tự thử lại tối đa 3 lần nếu lỗi và hiển thị kết quả trên màn hình sau khi hoàn tất. Nếu Drive vẫn lỗi, bài thi vẫn được nộp.
- PDF hiển thị nội dung câu hỏi, hình, công thức đã render bằng MathJax, đáp án hệ thống, lựa chọn của học sinh và điểm từng câu theo bố cục trang đối chiếu bài làm.
- PDF có tiêu đề **PHIẾU LÀM BÀI ONLINE**, tên Sở GD&ĐT TP Cần Thơ, Trường Tiểu học, THCS và THPT Quốc tế Hòa Bình, tên bài thi và khu vực có dòng ký tên cho học sinh.
- Tên file PDF trên Google Drive theo dạng `<Lớp>_<Tiêu đề bài kiểm tra>_<Tên đăng nhập>_<3 chữ số>.pdf`; tên lớp, bài thi và tài khoản được chuyển thành chữ không dấu.
- Máy chạy máy chủ cần cài Microsoft Edge hoặc Google Chrome để kết xuất PDF. Nếu trình duyệt không nằm ở vị trí mặc định, đặt biến môi trường `PDF_BROWSER_PATH` trỏ đến file thực thi của trình duyệt. Máy cần kết nối Internet để tải MathJax như các trang làm bài và quản trị.
- Mở [apps_script/Code.gs](./apps_script/Code.gs), sao chép nội dung vào một dự án tại [script.google.com](https://script.google.com), rồi vào **Project Settings → Script properties** và thêm `UPLOAD_TOKEN`. Tạo token riêng trên máy bằng `python -c "import secrets; print(secrets.token_urlsafe(32))"`; dùng cùng token cho Apps Script và localhost, không chia sẻ công khai.
- Triển khai bằng **Deploy → New deployment → Web app**, chọn **Execute as: Me** và **Who has access: Anyone**. Sao chép URL Web App kết thúc bằng `/exec`. Endpoint được bảo vệ bằng `UPLOAD_TOKEN`; không đăng URL kèm token lên nơi công khai.
- Đặt URL và đúng token vừa tạo thành biến môi trường Windows (thay giá trị mẫu), rồi khởi động lại cửa sổ máy chủ:
  ```powershell
  [Environment]::SetEnvironmentVariable("GOOGLE_APPS_SCRIPT_URL", "https://script.google.com/macros/s/DEPLOYMENT_ID/exec", "User")
  [Environment]::SetEnvironmentVariable("GOOGLE_APPS_SCRIPT_TOKEN", "DAN_TOKEN_RIENG_CUA_BAN", "User")
  ```
- Thư mục Drive mặc định là `1n4KAU_hVz-0TrhFBY_1BHU7qrsQsJ701`; có thể đổi bằng biến `GOOGLE_DRIVE_FOLDER_ID`. Apps Script chạy dưới tài khoản triển khai, vì vậy tài khoản đó phải có quyền chỉnh sửa thư mục. Không cần Google API key, service account JSON hoặc cài thư viện Google bổ sung.
- Sau khi đổi mã nguồn, cài gói theo `venv\Scripts\python.exe -m pip install -r requirements.txt` nếu cần. Máy chạy ứng dụng phải có Internet để gọi Apps Script.

---

## 👤 Tài khoản thử nghiệm mặc định

- **Học sinh:**
  - Tên đăng nhập: `nguyenvanan`
  - Mật khẩu: `123456`
- **Quản trị viên / Giáo viên:**
  - Tên đăng nhập: `admin`
  - Mật khẩu local mặc định: `admin123` (trên production dùng `ADMIN_DEFAULT_PASSWORD`)
  - URL Quản trị: `http://localhost:3000/admin`
