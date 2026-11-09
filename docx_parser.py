import os
import re
import shutil
import subprocess
import tempfile
import threading
import uuid
from io import BytesIO
from typing import Optional
import xml.etree.ElementTree as ET
from docx import Document
from docx.opc.constants import RELATIONSHIP_TYPE

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "static", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

OMML_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
DRAWING_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
VML_NS = "urn:schemas-microsoft-com:vml"

_WORD_MATHTYPE_LOCK = threading.Lock()


def _convert_mathtype_to_latex(doc_path: str, doc) -> Optional[bytes]:
    equation_relationships = []
    for image in doc._element.body.iter(f'{{{VML_NS}}}imagedata'):
        shape = image.getparent()
        while shape is not None and shape.tag.split('}')[-1] != 'shape':
            shape = shape.getparent()
        if shape is None or shape.get('{urn:schemas-microsoft-com:office:office}ole') is None:
            continue
        relationship_id = image.get(f'{{{R_NS}}}id')
        if relationship_id:
            equation_relationships.append(relationship_id)

    if not equation_relationships:
        return None

    powershell = shutil.which("powershell.exe") or shutil.which("powershell")
    if powershell is None:
        raise RuntimeError(
            "Cần Windows PowerShell, Microsoft Word và MathType để chuyển công thức MathType sang LaTeX."
        )

    script_path = os.path.join(os.path.dirname(__file__), "convert_mathtype_to_latex.ps1")
    with tempfile.TemporaryDirectory(prefix="pisq-mathtype-") as temp_dir:
        converted_docx = os.path.join(temp_dir, "converted.docx")
        with _WORD_MATHTYPE_LOCK:
            try:
                result = subprocess.run(
                    [
                        powershell,
                        "-NoProfile",
                        "-STA",
                        "-ExecutionPolicy",
                        "Bypass",
                        "-File",
                        script_path,
                        "-SourcePath",
                        os.path.abspath(doc_path),
                        "-OutputPath",
                        converted_docx,
                    ],
                    capture_output=True,
                    text=True,
                    timeout=300,
                    check=True,
                )
            except FileNotFoundError as exc:
                raise RuntimeError(
                    "Không tìm thấy Microsoft Word hoặc MathType. Hãy cài cả hai trên máy đang chạy PisQ."
                ) from exc
            except subprocess.TimeoutExpired as exc:
                raise RuntimeError(
                    "Microsoft Word/MathType chuyển đổi công thức quá lâu. Hãy kiểm tra Word "
                    "có đang hiện hộp thoại hoặc file Word có mở bình thường không."
                ) from exc
            except subprocess.CalledProcessError as exc:
                details = (exc.stderr or exc.stdout or str(exc)).strip()
                raise RuntimeError(
                    "Microsoft Word/MathType không thể chuyển công thức sang LaTeX. "
                    f"Chi tiết: {details[-1200:]}"
                ) from exc

        match = re.search(r"ConvertedCount=(\d+)", result.stdout)
        if not match or int(match.group(1)) != len(equation_relationships):
            converted_count = match.group(1) if match else "không xác định"
            raise RuntimeError(
                "MathType chuyển đổi không đủ công thức sang LaTeX "
                f"(đã chuyển: {converted_count}, trong tài liệu: {len(equation_relationships)})."
            )

        try:
            with open(converted_docx, "rb") as converted_file:
                return converted_file.read()
        except FileNotFoundError as exc:
            raise RuntimeError("MathType không tạo được tài liệu đã chuyển sang LaTeX.") from exc


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

    elif tag == 'acc':
        acc_pr = elem.find(f'{{{OMML_NS}}}accPr')
        accent = acc_pr.find(f'{{{OMML_NS}}}chr') if acc_pr is not None else None
        accent_value = accent.get(f'{{{OMML_NS}}}val', '') if accent is not None else ''
        e = elem.find(f'{{{OMML_NS}}}e')
        expression = omml_node_to_latex(e) if e is not None else ''
        accent_commands = {
            '\u20d7': '\\vec',
            '\u20d6': '\\overleftarrow',
            '\u0302': '\\hat',
            '\u0303': '\\tilde',
            '\u0305': '\\bar',
        }
        command = accent_commands.get(accent_value)
        if command:
            return f"{command}{{{expression}}}"
        if accent_value:
            return f"\\overset{{{accent_value}}}{{{expression}}}"
        return expression

    elif tag == 'func':
        fName = elem.find(f'{{{OMML_NS}}}fName')
        e = elem.find(f'{{{OMML_NS}}}e')
        fn_str = omml_node_to_latex(fName) if fName is not None else ""
        e_str = omml_node_to_latex(e) if e is not None else ""
        return f"{fn_str} {e_str}"

    elif tag == 'nary':
        nary_pr = elem.find(f'{{{OMML_NS}}}naryPr')
        chr_elem = nary_pr.find(f'{{{OMML_NS}}}chr') if nary_pr is not None else None
        operator = chr_elem.get(f'{{{OMML_NS}}}val', '') if chr_elem is not None else ''
        operator_commands = {
            '\u222b': '\\int',
            '\u222c': '\\iint',
            '\u222d': '\\iiint',
            '\u2211': '\\sum',
            '\u220f': '\\prod',
            '\u222e': '\\oint',
        }
        command = operator_commands.get(operator, '\\int')
        sub = elem.find(f'{{{OMML_NS}}}sub')
        sup = elem.find(f'{{{OMML_NS}}}sup')
        e = elem.find(f'{{{OMML_NS}}}e')
        sub_str = f"_{{{omml_node_to_latex(sub)}}}" if sub is not None else ""
        sup_str = f"^{{{omml_node_to_latex(sup)}}}" if sup is not None else ""
        e_str = omml_node_to_latex(e) if e is not None else ""
        return f"{command}{sub_str}{sup_str} {e_str}"

    elif tag in ['limLow', 'limUpp']:
        e = elem.find(f'{{{OMML_NS}}}e')
        limit = elem.find(f'{{{OMML_NS}}}lim')
        e_str = omml_node_to_latex(e) if e is not None else ""
        limit_str = omml_node_to_latex(limit) if limit is not None else ""
        if tag == 'limLow':
            return f"{{{e_str}}}_{{{limit_str}}}"
        return f"{{{e_str}}}^{{{limit_str}}}"

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


def _enhance_math_alpha(alpha):
    alpha_lut = [
        round(255 * (value / 255) ** 0.65)
        for value in range(256)
    ]
    return alpha.point(alpha_lut)


def extract_images_from_element(element, doc, mathtype_images=None) -> list:
    """
    Trích xuất ảnh DrawingML/VML và lưu cùng thông tin hiển thị MathType từ Word.
    """
    image_references = [
        {
            "relationship_id": blip.get(f'{{{R_NS}}}embed'),
            "inline_math": False,
            "style": "",
        }
        for blip in element.findall(f'.//{{{DRAWING_NS}}}blip')
    ]
    for image in element.findall(f'.//{{{VML_NS}}}imagedata'):
        shape = image.getparent()
        while shape is not None and shape.tag.split('}')[-1] != 'shape':
            shape = shape.getparent()

        shape_style = shape.get('style', '') if shape is not None else ''
        is_math_type = (
            shape is not None
            and shape.get('{urn:schemas-microsoft-com:office:office}ole') is not None
        )
        display_dimensions = []
        if is_math_type:
            for dimension in ('width', 'height'):
                match = re.search(
                    rf'(?:^|;)\s*{dimension}\s*:\s*(\d+(?:\.\d+)?)\s*(pt|px|in|cm|mm)\b',
                    shape_style,
                    re.IGNORECASE,
                )
                if match:
                    value = float(match.group(1))
                    if 0 < value <= 1200:
                        display_dimensions.append(
                            f'{dimension}:{match.group(1)}{match.group(2).lower()}'
                        )

        image_references.append({
            "relationship_id": image.get(f'{{{R_NS}}}id'),
            "inline_math": is_math_type,
            "style": ';'.join(display_dimensions),
        })

    extracted_images = []
    for reference in image_references:
        relationship_id = reference["relationship_id"]
        if not relationship_id or relationship_id not in doc.part.related_parts:
            continue

        image_part = doc.part.related_parts[relationship_id]
        content_type = image_part.content_type.lower()
        extension_by_type = {
            "image/png": ".png",
            "image/jpeg": ".jpg",
            "image/gif": ".gif",
            "image/svg+xml": ".svg",
            "image/webp": ".webp",
            "image/bmp": ".bmp",
        }
        extension = extension_by_type.get(content_type)
        image_data = image_part.blob
        rendered_by_word = (
            reference["inline_math"]
            and mathtype_images is not None
            and relationship_id in mathtype_images
        )
        if rendered_by_word:
            image_data = mathtype_images[relationship_id]
            extension = ".png"
            try:
                from PIL import Image, ImageOps
            except ModuleNotFoundError as exc:
                if exc.name != "PIL":
                    raise
                raise RuntimeError(
                    "Cần cài Pillow để xử lý ảnh công thức do Microsoft Word kết xuất."
                ) from exc

            try:
                with Image.open(BytesIO(image_data)) as image:
                    alpha = ImageOps.invert(image.convert("RGB").convert("L"))
                    alpha = _enhance_math_alpha(alpha)
                    equation_image = Image.new("RGBA", image.size, (255, 255, 255, 0))
                    equation_image.putalpha(alpha)
                    converted = BytesIO()
                    equation_image.save(converted, format="PNG")
                    image_data = converted.getvalue()
            except (OSError, ValueError) as exc:
                raise ValueError(
                    "Không thể xử lý ảnh công thức MathType do Microsoft Word kết xuất."
                ) from exc

        if extension is None and not rendered_by_word:
            try:
                from PIL import Image, ImageOps
            except ModuleNotFoundError as exc:
                if exc.name != "PIL":
                    raise
                raise RuntimeError(
                    "Cần cài Pillow để chuyển công thức/hình VML sang định dạng hiển thị."
                ) from exc

            try:
                with Image.open(BytesIO(image_data)) as image:
                    image_format = image.format
                    if image_format in {"WMF", "EMF"}:
                        image.load(dpi=300)
                    converted = BytesIO()
                    if reference["inline_math"] and image_format in {"WMF", "EMF"}:
                        alpha = ImageOps.invert(image.convert("RGB").convert("L"))
                        alpha = _enhance_math_alpha(alpha)
                        equation_image = Image.new("RGBA", image.size, (255, 255, 255, 0))
                        equation_image.putalpha(alpha)
                    else:
                        equation_image = image.convert("RGBA")
                    equation_image.save(converted, format="PNG", dpi=(300, 300))
                    image_data = converted.getvalue()
                    extension = ".png"
            except (OSError, ValueError) as exc:
                raise ValueError(
                    f"Không thể chuyển ảnh/công thức nhúng ({content_type}) sang định dạng hiển thị."
                ) from exc

        filename = f"img_{uuid.uuid4().hex[:12]}{extension}"
        file_path = os.path.join(UPLOAD_DIR, filename)
        with open(file_path, "wb") as f:
            f.write(image_data)

        extracted_images.append({
            "url": f"/static/uploads/{filename}",
            "inline_math": reference["inline_math"],
            "style": reference["style"],
        })

    return extracted_images

def parse_paragraph_to_html(p, doc, mathtype_images=None) -> tuple[str, bool]:
    """
    Bóc tách đoạn văn:
    - Text thường
    - Ảnh nhúng inline -> <img src="..." class="inline-img">
    - Công thức toán OMML -> $LaTeX$
    - Phát hiện xem đoạn này có bị gạch chân (Underline) hay không.
    """
    parts = []
    has_underline = False

    def append_child_content(child):
        nonlocal has_underline
        tag = child.tag.split('}')[-1]

        if tag in ['oMath', 'oMathPara']:
            latex = omml_node_to_latex(child).strip()
            if latex:
                parts.append(f" ${latex}$ ")
            return

        if tag == 'r':
            run_properties = child.find(f'{{{W_NS}}}rPr')
            underline = run_properties.find(f'{{{W_NS}}}u') if run_properties is not None else None
            if underline is not None and underline.get(f'{{{W_NS}}}val') != 'none':
                has_underline = True

            for run_child in child:
                run_tag = run_child.tag.split('}')[-1]
                if run_tag == 't' and run_child.text:
                    parts.append(run_child.text)
                elif run_tag in ['tab']:
                    parts.append(' ')
                elif run_tag in ['br', 'cr']:
                    parts.append('<br/>')
                elif run_tag in ['drawing', 'pict', 'object']:
                    for image in extract_images_from_element(run_child, doc, mathtype_images):
                        if image["inline_math"]:
                            style_attribute = (
                                f' style="{image["style"]}"' if image["style"] else ''
                            )
                            parts.append(
                                f'<img src="{image["url"]}" class="inline-math-img"{style_attribute} alt="Công thức MathType" />'
                            )
                        else:
                            parts.append(
                                f'<div class="exam-img-box"><img src="{image["url"]}" class="exam-img" alt="Hình ảnh câu hỏi" /></div>'
                            )
                elif run_tag not in ['rPr']:
                    append_child_content(run_child)
            return

        if tag in ['drawing', 'pict', 'object']:
            for image in extract_images_from_element(child, doc, mathtype_images):
                if image["inline_math"]:
                    style_attribute = (
                        f' style="{image["style"]}"' if image["style"] else ''
                    )
                    parts.append(
                        f'<img src="{image["url"]}" class="inline-math-img"{style_attribute} alt="Công thức MathType" />'
                    )
                else:
                    parts.append(
                        f'<div class="exam-img-box"><img src="{image["url"]}" class="exam-img" alt="Hình ảnh câu hỏi" /></div>'
                    )
            return

        for nested_child in child:
            append_child_content(nested_child)

    for child in p._p:
        append_child_content(child)

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
    converted_docx = _convert_mathtype_to_latex(doc_path, doc)
    if converted_docx is not None:
        doc = Document(BytesIO(converted_docx))
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

        # A question must belong to an explicitly tagged section.
        if current_sec is None:
            if re.match(r'^(Câu|Question|Bài)\s*\d+[\.:]', content, re.IGNORECASE):
                raise ValueError(
                    "Câu hỏi chưa thuộc phần nào. Hãy thêm thẻ <#g1>, <#g2>, <#g3> hoặc <#g4> trước câu hỏi."
                )
            continue

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
            opt_letter = opt_match.group(1)
            opt_letter = (
                opt_letter.lower()
                if current_sec["section_type"] in ["g2", "g4"]
                else opt_letter.upper()
            )
            opt_content = opt_match.group(2).strip()

            current_q["options"].append({
                "label": opt_letter,
                "content": opt_content,
                "is_correct": is_underlined
            })
            continue

        # 4. Đáp án chuẩn của câu trả lời ngắn phải có tiền tố DA. hoặc DA:
        ans_match = re.match(r'^DA[.:]\s*(.*)', content, re.IGNORECASE)
        if ans_match and current_q is not None:
            ans_val = ans_match.group(1).strip()
            current_q["short_answer"] = ans_val
            continue
        if (
            current_q is not None
            and current_sec["section_type"] == "g3"
            and re.match(r'^(DA\b|Đáp án\b|Answer\b)', content, re.IGNORECASE)
        ):
            raise ValueError(
                "Đáp án câu trả lời ngắn phải bắt đầu bằng tiền tố bắt buộc 'DA.' hoặc 'DA:', ví dụ: DA. 12."
            )

        # 5. Nếu không khớp phương án mà đang trong câu hỏi -> Đây là dòng mô tả/hình ảnh tiếp nối của câu hỏi
        if current_q is not None and not current_q["options"]:
            current_q["content"] += f"<br/>{content}"
        elif current_q is not None and current_q["options"]:
            # Dòng tiếp nối của phương án trước đó
            current_q["options"][-1]["content"] += f"<br/>{content}"

    for section in sections:
        if section["section_type"] != "g3" or not section["questions"]:
            continue

        questions = section["questions"]
        if all(
            not question["short_answer"]
            and len(question["options"]) == 4
            and {option["label"] for option in question["options"]} == {"A", "B", "C", "D"}
            and sum(option["is_correct"] for option in question["options"]) == 1
            for question in questions
        ):
            section["section_type"] = "g1"

    return sections
