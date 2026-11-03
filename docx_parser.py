import os
import re
import uuid
import xml.etree.ElementTree as ET
from docx import Document
from docx.opc.constants import RELATIONSHIP_TYPE

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "static", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

OMML_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
DRAWING_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

def omml_node_to_latex(elem) -> str:
    """
    Chuyển đổi các thẻ toán học OMML (Office Math) sang cú pháp LaTeX chuẩn.
    """
    tag = elem.tag.split('}')[-1]

    if tag in ['oMath', 'oMathPara']:
        return "".join(omml_node_to_latex(c) for c in elem)

    elif tag == 'f':
        num = elem.find(f'{{{OMML_NS}}}num')
        den = elem.find(f'{{{OMML_NS}}}den')
        num_str = omml_node_to_latex(num) if num is not None else ""
        den_str = omml_node_to_latex(den) if den is not None else ""
        return f"\\frac{{{num_str}}}{{{den_str}}}"

    elif tag == 'sSup':
        e = elem.find(f'{{{OMML_NS}}}e')
        sup = elem.find(f'{{{OMML_NS}}}sup')
        e_str = omml_node_to_latex(e) if e is not None else ""
        sup_str = omml_node_to_latex(sup) if sup is not None else ""
        return f"{{{e_str}}}^{{{sup_str}}}"

    elif tag == 'sSub':
        e = elem.find(f'{{{OMML_NS}}}e')
        sub = elem.find(f'{{{OMML_NS}}}sub')
        e_str = omml_node_to_latex(e) if e is not None else ""
        sub_str = omml_node_to_latex(sub) if sub is not None else ""
        return f"{{{e_str}}}_{{{sub_str}}}"

    elif tag == 'sSubSup':
        e = elem.find(f'{{{OMML_NS}}}e')
        sub = elem.find(f'{{{OMML_NS}}}sub')
        sup = elem.find(f'{{{OMML_NS}}}sup')
        e_str = omml_node_to_latex(e) if e is not None else ""
        sub_str = omml_node_to_latex(sub) if sub is not None else ""
        sup_str = omml_node_to_latex(sup) if sup is not None else ""
        return f"{{{e_str}}}_{{{sub_str}}}^{{{sup_str}}}"

    elif tag == 'rad':
        deg = elem.find(f'{{{OMML_NS}}}deg')
        e = elem.find(f'{{{OMML_NS}}}e')
        deg_str = f"[{omml_node_to_latex(deg)}]" if (deg is not None and len(deg) > 0) else ""
        e_str = omml_node_to_latex(e) if e is not None else ""
        return f"\\sqrt{deg_str}{{{e_str}}}"

    elif tag == 'd':
        # Delimiters (ngoặc đơn, ngoặc vuông, v.v.)
        beg_chr = "("
        end_chr = ")"
        dPr = elem.find(f'{{{OMML_NS}}}dPr')
        if dPr is not None:
            beg = dPr.find(f'{{{OMML_NS}}}begChr')
            if beg is not None and beg.get(f'{{{OMML_NS}}}val'):
                beg_chr = beg.get(f'{{{OMML_NS}}}val')
            end = dPr.find(f'{{{OMML_NS}}}endChr')
            if end is not None and end.get(f'{{{OMML_NS}}}val'):
                end_chr = end.get(f'{{{OMML_NS}}}val')
        e = elem.find(f'{{{OMML_NS}}}e')
        e_str = omml_node_to_latex(e) if e is not None else ""
        # Escape brackets for LaTeX if needed
        beg_esc = "\\" + beg_chr if beg_chr in ["{", "}"] else beg_chr
        end_esc = "\\" + end_chr if end_chr in ["{", "}"] else end_chr
        return f"\\left{beg_esc} {e_str} \\right{end_esc}"

    elif tag == 'bar':
        e = elem.find(f'{{{OMML_NS}}}e')
        return f"\\overline{{{omml_node_to_latex(e) if e is not None else ''}}}"

    elif tag == 'func':
        fName = elem.find(f'{{{OMML_NS}}}fName')
        e = elem.find(f'{{{OMML_NS}}}e')
        fn_str = omml_node_to_latex(fName) if fName is not None else ""
        e_str = omml_node_to_latex(e) if e is not None else ""
        return f"{fn_str} {e_str}"

    elif tag == 'nary':
        sub = elem.find(f'{{{OMML_NS}}}sub')
        sup = elem.find(f'{{{OMML_NS}}}sup')
        e = elem.find(f'{{{OMML_NS}}}e')
        sub_str = f"_{{{omml_node_to_latex(sub)}}}" if sub is not None else ""
        sup_str = f"^{{{omml_node_to_latex(sup)}}}" if sup is not None else ""
        e_str = omml_node_to_latex(e) if e is not None else ""
        return f"\\int{sub_str}{sup_str} {e_str}"

    elif tag == 'r':
        t = elem.find(f'{{{OMML_NS}}}t')
        if t is not None and t.text:
            txt = t.text
            # Chuyển đổi một số ký hiệu thông dụng nếu cần
            txt = txt.replace('<=', '\\le ').replace('>=', '\\ge ').replace('!=', '\\ne ')
            return txt
        return ""

    elif tag in ['num', 'den', 'e', 'sub', 'sup', 'deg', 'fName']:
        return "".join(omml_node_to_latex(c) for c in elem)

    else:
        # Fallback cho các thẻ khác
        res = []
        for c in elem:
            res.append(omml_node_to_latex(c))
        return "".join(res)

def extract_images_from_element(element, doc) -> list:
    """
    Trích xuất hình ảnh Inline (w:drawing, a:blip) từ một thẻ XML và lưu vào static/uploads.
    Trả về danh sách URL ảnh đã lưu.
    """
    image_urls = []
    # Tìm tất cả thẻ blip có liên kết hình ảnh
    blips = element.findall(f'.//{{{DRAWING_NS}}}blip')
    for blip in blips:
        rId = blip.get(f'{{{R_NS}}}embed')
        if rId and rId in doc.part.related_parts:
            image_part = doc.part.related_parts[rId]
            # Xác định extension từ content_type
            content_type = image_part.content_type
            ext = ".png"
            if "jpeg" in content_type or "jpg" in content_type:
                ext = ".jpg"
            elif "gif" in content_type:
                ext = ".gif"
            elif "svg" in content_type:
                ext = ".svg"

            filename = f"img_{uuid.uuid4().hex[:12]}{ext}"
            file_path = os.path.join(UPLOAD_DIR, filename)
            with open(file_path, "wb") as f:
                f.write(image_part.blob)

            image_urls.append(f"/static/uploads/{filename}")

    return image_urls

def parse_paragraph_to_html(p, doc) -> tuple[str, bool]:
    """
    Bóc tách đoạn văn:
    - Text thường
    - Ảnh nhúng inline -> <img src="..." class="inline-img">
    - Công thức toán OMML -> $LaTeX$
    - Phát hiện xem đoạn này có bị gạch chân (Underline) hay không.
    """
    parts = []
    has_underline = False

    for child in p._p:
        tag = child.tag.split('}')[-1]

        # 1. Đoạn text / inline image trong w:r
        if tag == 'r':
            # Kiểm tra gạch chân
            rPr = child.find(f'{{{W_NS}}}rPr')
            if rPr is not None:
                u = rPr.find(f'{{{W_NS}}}u')
                if u is not None:
                    u_val = u.get(f'{{{W_NS}}}val')
                    if u_val is None or u_val != 'none':
                        has_underline = True

            # Kiểm tra ảnh nhúng trong w:r
            imgs = extract_images_from_element(child, doc)
            for img_url in imgs:
                parts.append(f'<div class="exam-img-box"><img src="{img_url}" class="exam-img" alt="Hình ảnh câu hỏi" /></div>')

            # Lấy text
            t = child.find(f'{{{W_NS}}}t')
            if t is not None and t.text:
                parts.append(t.text)

        # 2. Công thức toán OMML
        elif tag in ['oMath', 'oMathPara']:
            latex = omml_node_to_latex(child).strip()
            if latex:
                parts.append(f" ${latex}$ ")

        # 3. Ảnh nhúng nằm trực tiếp trong w:drawing ngoài w:r
        elif tag == 'drawing':
            imgs = extract_images_from_element(child, doc)
            for img_url in imgs:
                parts.append(f'<div class="exam-img-box"><img src="{img_url}" class="exam-img" alt="Hình ảnh câu hỏi" /></div>')

    content = "".join(parts).strip()
    return content, has_underline

def parse_docx_file(doc_path: str) -> list:
    """
    Bóc tách toàn diện file đề thi .docx theo cấu trúc 4 phần của GDPT 2018:
    - <#g1>: Phần I (Trắc nghiệm nhiều lựa chọn)
    - <#g2>: Phần II (Trắc nghiệm đúng/sai)
    - <#g3>: Phần III (Trả lời ngắn)
    - <#g4>: Phần IV (Tự luận / Tiếng Anh)
    """
    doc = Document(doc_path)
    sections = []
    current_sec = None
    current_q = None

    for p in doc.paragraphs:
        content, is_underlined = parse_paragraph_to_html(p, doc)
        if not content:
            continue

        # 1. Nhận diện thẻ Section <#g1> đến <#g4>
        tag_match = re.search(r'<#(g[1-4])>', content, re.IGNORECASE)
        if tag_match:
            sec_type = tag_match.group(1).lower()
            default_titles = {
                "g1": "PHẦN I. Câu trắc nghiệm nhiều phương án lựa chọn",
                "g2": "PHẦN II. Trắc nghiệm lựa chọn đúng sai",
                "g3": "PHẦN III. Câu hỏi trắc nghiệm trả lời ngắn",
                "g4": "PHẦN IV. Tự luận"
            }
            # Lấy tiêu đề sau thẻ tag
            title_text = re.sub(r'<#g[1-4]>', '', content, flags=re.IGNORECASE).strip()
            if not title_text:
                title_text = default_titles.get(sec_type, f"Phần {sec_type.upper()}")

            current_sec = {
                "section_type": sec_type,
                "title": title_text,
                "questions": []
            }
            sections.append(current_sec)
            current_q = None
            continue

        # Nếu chưa gặp tag nào mà đã xuất hiện câu hỏi, gán mặc định vào g1
        if current_sec is None:
            current_sec = {
                "section_type": "g1",
                "title": "PHẦN I. Câu trắc nghiệm nhiều phương án lựa chọn",
                "questions": []
            }
            sections.append(current_sec)

        # 2. Nhận diện Bắt đầu câu hỏi ("Câu 1.", "Câu 1:", "Question 1:", "Bài 1:",...)
        q_match = re.match(r'^(Câu|Question|Bài)\s*(\d+)[\.:]\s*(.*)', content, re.IGNORECASE | re.DOTALL)
        if q_match:
            q_num = q_match.group(2)
            q_content = q_match.group(3).strip()
            current_q = {
                "number": int(q_num),
                "content": q_content,
                "options": [],
                "short_answer": ""
            }
            current_sec["questions"].append(current_q)
            continue

        # 3. Nhận diện Phương án ("A.", "B.", "C.", "D." hoặc "a)", "b)", "c)", "d)")
        opt_match = re.match(r'^([A-Da-d])[\.:\)]\s*(.*)', content, re.DOTALL)
        if opt_match and current_q is not None:
            opt_letter = opt_match.group(1).upper()
            opt_content = opt_match.group(2).strip()

            current_q["options"].append({
                "label": opt_letter,
                "content": opt_content,
                "is_correct": is_underlined
            })
            continue

        # 4. Nhận diện đáp án ngắn (nếu có ghi "Đáp án: ...")
        ans_match = re.match(r'^(Đáp án|Answer)[\.:]\s*(.*)', content, re.IGNORECASE)
        if ans_match and current_q is not None:
            ans_val = ans_match.group(2).strip()
            current_q["short_answer"] = ans_val
            continue

        # 5. Nếu không khớp phương án mà đang trong câu hỏi -> Đây là dòng mô tả/hình ảnh tiếp nối của câu hỏi
        if current_q is not None and not current_q["options"]:
            current_q["content"] += f"<br/>{content}"
        elif current_q is not None and current_q["options"]:
            # Dòng tiếp nối của phương án trước đó
            current_q["options"][-1]["content"] += f"<br/>{content}"

    return sections
