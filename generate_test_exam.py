import docx
from docx import Document
from docx.oxml import parse_xml
import docx_parser

def create_sample_exam():
    doc = Document()

    # Section 1: Trắc nghiệm 4 phương án
    doc.add_paragraph('<#g1> PHẦN I. Câu trắc nghiệm nhiều phương án lựa chọn')

    # Câu 1
    doc.add_paragraph('Câu 1: Thẻ < title > dùng để đặt tiêu đề của trang web được đặt bên trong phần tử nào?')
    doc.add_paragraph('A. Phần tử <head>')
    p1b = doc.add_paragraph()
    r1b = p1b.add_run('B. Phần tử <body>')
    r1b.underline = True
    doc.add_paragraph('C. Phần tử <p>')
    doc.add_paragraph('D. Phần tử <div>')

    # Câu 2 có toán học
    p2 = doc.add_paragraph('Câu 2: Nghiệm của phương trình ')
    omml_xml = (
        '<m:oMath xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math">'
        '<m:f>'
        '<m:num><m:r><m:t>x + 1</m:t></m:r></m:num>'
        '<m:den><m:r><m:t>2</m:t></m:r></m:den>'
        '</m:f>'
        '<m:r><m:t> = 3</m:t></m:r>'
        '</m:oMath>'
    )
    p2._p.append(parse_xml(omml_xml))
    p2.add_run(' là:')
    doc.add_paragraph('A. x = 4')
    p2b = doc.add_paragraph()
    r2b = p2b.add_run('B. x = 5')
    r2b.underline = True
    doc.add_paragraph('C. x = 6')
    doc.add_paragraph('D. x = 7')

    # Section 2: Đúng sai
    doc.add_paragraph('<#g2> PHẦN II. Trắc nghiệm lựa chọn đúng sai')
    doc.add_paragraph('Câu 3: Cho hàm số f(x) = x^2 - 4x + 3. Xét tính đúng sai của các khẳng định sau:')
    p3a = doc.add_paragraph()
    r3a = p3a.add_run('a) Hàm số đồng biến trên khoảng (2; +∞)')
    r3a.underline = True
    p3b = doc.add_paragraph()
    r3b = p3b.add_run('b) Đồ thị hàm số đi qua điểm M(0; 3)')
    r3b.underline = True
    doc.add_paragraph('c) Giá trị nhỏ nhất của hàm số bằng 0')
    p3d = doc.add_paragraph()
    r3d = p3d.add_run('d) Phương trình f(x) = 0 có hai nghiệm phân biệt x = 1 và x = 3')
    r3d.underline = True

    # Section 3: Trả lời ngắn
    doc.add_paragraph('<#g3> PHẦN III. Câu hỏi trắc nghiệm trả lời ngắn')
    doc.add_paragraph('Câu 4: Tìm số nghiệm thực của phương trình x^3 - 3x + 1 = 0.')
    doc.add_paragraph('Đáp án: 3')

    # Section 4: Tự luận
    doc.add_paragraph('<#g4> PHẦN IV. Tự luận')
    doc.add_paragraph('Câu 5: Hãy giải thích vai trò của cơ chế CSS Flexbox trong việc xây dựng giao diện web đáp ứng (responsive web design).')

    file_path = 'test_exam.docx'
    doc.save(file_path)
    print(f"[OK] Đã tạo thành công file: {file_path}")

    # Test parse
    parsed = docx_parser.parse_docx_file(file_path)
    print(f"[OK] Đã phân tích thành công {len(parsed)} phần:")
    for s in parsed:
        print(f"-> {s['section_type'].upper()}: {s['title']} ({len(s['questions'])} câu)")
        for q in s['questions']:
            print(f"   Q{q['number']}: {q['content']}")
            for opt in q['options']:
                print(f"     [{opt['label']}] {opt['content']} (Đúng: {opt['is_correct']})")
            if q.get('short_answer'):
                print(f"     Đáp án ngắn: {q['short_answer']}")

if __name__ == '__main__':
    create_sample_exam()
