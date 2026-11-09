from html.parser import HTMLParser
import base64
import mimetypes
import os
import re
import shutil
import subprocess
import tempfile
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import unquote, urlsplit

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from xml.sax.saxutils import escape


def _register_vietnamese_font() -> None:
    configured_path = os.getenv("PDF_FONT_PATH")
    font_candidates = [
        configured_path,
        os.path.join(os.getenv("WINDIR", r"C:\Windows"), "Fonts", "arial.ttf"),
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
    ]
    regular_path = next(
        (path for path in font_candidates if path and os.path.isfile(path)),
        None,
    )
    if not regular_path:
        raise RuntimeError(
            "Không tìm thấy font Unicode để xuất tiếng Việt. "
            "Hãy cài DejaVu Sans hoặc đặt biến PDF_FONT_PATH."
        )

    bold_candidates = [
        os.path.join(os.path.dirname(regular_path), "arialbd.ttf"),
        os.path.join(os.path.dirname(regular_path), "DejaVuSans-Bold.ttf"),
    ]
    bold_path = next((path for path in bold_candidates if os.path.isfile(path)), regular_path)
    if "PisQUnicode" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("PisQUnicode", regular_path))
        pdfmetrics.registerFont(TTFont("PisQUnicode-Bold", bold_path))
        pdfmetrics.registerFontFamily(
            "PisQUnicode",
            normal="PisQUnicode",
            bold="PisQUnicode-Bold",
            italic="PisQUnicode",
            boldItalic="PisQUnicode-Bold",
        )


def _paragraph(value: Any, style: ParagraphStyle) -> Paragraph:
    return Paragraph(escape(str(value if value is not None else "-")), style)


class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        if tag in {"br", "p", "div", "li"}:
            self.parts.append("\n")
        elif tag == "img":
            alt = dict(attrs).get("alt")
            if alt:
                self.parts.append(alt)

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def _plain_text(value: Any) -> str:
    extractor = _HTMLTextExtractor()
    extractor.feed(str(value if value is not None else "-"))
    return re.sub(r"\s+", " ", "".join(extractor.parts)).strip()


class _ReportLabHTMLConverter(HTMLParser):
    _INLINE_TAGS = {
        "b": "b",
        "strong": "b",
        "i": "i",
        "em": "i",
        "u": "u",
        "sup": "super",
        "sub": "sub",
        "strike": "strike",
        "s": "strike",
        "del": "strike",
    }
    _BLOCK_TAGS = {"p", "div", "section", "article", "ul", "ol"}
    def __init__(self, embed_images: bool = False) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: List[str] = []
        self.open_tags: List[str] = []
        self.embed_images = embed_images

    def _line_break(self) -> None:
        if self.parts and not self.parts[-1].endswith("<br/>"):
            self.parts.append("<br/>")

    def _image_markup(self, attrs: List[Tuple[str, Optional[str]]]) -> str:
        attributes = dict(attrs)
        source = attributes.get("src") or ""
        alt = escape(attributes.get("alt") or "Hình ảnh")
        parsed = urlsplit(source)
        relative_path = unquote(parsed.path).lstrip("/")
        if not relative_path.startswith("static/uploads/"):
            return f"[{alt}]"

        upload_root = os.path.realpath(
            os.path.join(os.path.dirname(__file__), "static", "uploads")
        )
        image_path = os.path.realpath(
            os.path.join(os.path.dirname(__file__), relative_path.replace("/", os.sep))
        )
        if os.path.commonpath((upload_root, image_path)) != upload_root:
            return f"[{alt}]"
        if not os.path.isfile(image_path):
            return f"[Không tìm thấy hình: {alt}]"

        try:
            image_width, image_height = ImageReader(image_path).getSize()
        except (OSError, ValueError):
            return f"[Không thể hiển thị hình: {alt}]"

        inline_math = "inline-math-img" in (attributes.get("class") or "").split()
        max_width = 170 if inline_math else 475
        max_height = 55 if inline_math else 280
        scale = min(max_width / image_width, max_height / image_height, 1)
        width = max(1, image_width * scale)
        height = max(1, image_height * scale)
        if self.embed_images:
            mime_type = mimetypes.guess_type(image_path)[0] or "application/octet-stream"
            with open(image_path, "rb") as image_file:
                source = (
                    f"data:{mime_type};base64,"
                    f"{base64.b64encode(image_file.read()).decode('ascii')}"
                )
        else:
            source = escape(image_path)
        return (
            f'<img src="{source}" width="{width:.1f}" '
            f'height="{height:.1f}" valign="middle"/>'
        )

    def handle_starttag(
        self, tag: str, attrs: List[Tuple[str, Optional[str]]]
    ) -> None:
        if tag == "img":
            self.parts.append(self._image_markup(attrs))
        elif tag == "br":
            self._line_break()
        elif tag in self._BLOCK_TAGS:
            self._line_break()
        elif tag == "li":
            self._line_break()
            self.parts.append("&#8226;&nbsp;")
        elif tag in self._INLINE_TAGS:
            output_tag = self._INLINE_TAGS[tag]
            self.parts.append(f"<{output_tag}>")
            self.open_tags.append(output_tag)
        elif tag in {"td", "th"}:
            if self.parts and not self.parts[-1].endswith("<br/>"):
                self.parts.append("&nbsp;&nbsp;|&nbsp;&nbsp;")
        elif tag in {"pre", "code"}:
            self.parts.append('<font name="Courier">')
            self.open_tags.append("font")

    def handle_endtag(self, tag: str) -> None:
        if tag in self._BLOCK_TAGS or tag == "li":
            self._line_break()
            return
        if tag in {"td", "th"}:
            self.parts.append("&nbsp;&nbsp;")
            return
        output_tag = self._INLINE_TAGS.get(tag)
        if tag in {"pre", "code"}:
            output_tag = "font"
        if output_tag and output_tag in self.open_tags:
            while self.open_tags:
                opened = self.open_tags.pop()
                self.parts.append(f"</{opened}>")
                if opened == output_tag:
                    break

    def handle_data(self, data: str) -> None:
        self.parts.append(escape(data))

    def markup(self) -> str:
        while self.open_tags:
            self.parts.append(f"</{self.open_tags.pop()}>")
        return "".join(self.parts).strip()


def _reportlab_markup(value: Any) -> str:
    converter = _ReportLabHTMLConverter()
    converter.feed(str(value if value is not None else "-"))
    return converter.markup() or "-"


def _browser_markup(value: Any) -> str:
    converter = _ReportLabHTMLConverter(embed_images=True)
    converter.feed(str(value if value is not None else "-"))
    return converter.markup() or "-"


def _find_pdf_browser() -> Optional[str]:
    configured_path = os.getenv("PDF_BROWSER_PATH")
    candidates = [
        configured_path,
        os.path.join(
            os.getenv("PROGRAMFILES(X86)", r"C:\Program Files (x86)"),
            "Microsoft",
            "Edge",
            "Application",
            "msedge.exe",
        ),
        os.path.join(
            os.getenv("PROGRAMFILES", r"C:\Program Files"),
            "Microsoft",
            "Edge",
            "Application",
            "msedge.exe",
        ),
        os.path.join(
            os.getenv("PROGRAMFILES", r"C:\Program Files"),
            "Google",
            "Chrome",
            "Application",
            "chrome.exe",
        ),
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
        "/usr/bin/google-chrome",
    ]
    browser = next(
        (path for path in candidates if path and os.path.isfile(path)),
        None,
    )
    return browser or next(
        (
            shutil.which(name)
            for name in ("chromium", "chromium-browser", "google-chrome", "chrome")
            if shutil.which(name)
        ),
        None,
    )


def _comparison_html(
    exam_title: str,
    student_name: str,
    username: str,
    class_name: Optional[str],
    score: Any,
    total_score: Any,
    submitted_at: Any,
    status: Optional[str],
    sections: List[Dict[str, Any]],
) -> str:
    def safe(value: Any) -> str:
        return escape(str(value if value is not None else "-"))

    def content(value: Any) -> str:
        return _browser_markup(value)

    def tag(label: str, kind: str) -> str:
        return f'<span class="tag {kind}">{safe(label)}</span>'

    def answer_block(title: str, value: Any, empty: bool = False) -> str:
        return (
            f'<div class="answer-column"><strong>{safe(title)}</strong>'
            f'<div class="answer-content{" empty" if empty else ""}">'
            f'{content(value)}</div></div>'
        )

    status_labels = {
        "submitted": "Đã nộp bài",
        "graded": "Đã chấm điểm",
        "timed_out": "Hết giờ",
    }
    is_graded = status in ("submitted", "graded", "timed_out")
    rendered_sections = []
    for section in sections:
        questions_html = []
        for question in section.get("questions", []):
            earned = float(question.get("earned_points") or 0)
            maximum = float(question.get("possible_points") or 0)
            if not is_graded:
                state_label = "Chưa chấm"
            elif question.get("section_type") == "g4":
                state_label = "Chờ chấm tự luận"
            elif earned >= maximum and maximum > 0:
                state_label = "Đúng"
            elif earned > 0:
                state_label = "Đúng một phần"
            elif question.get("student_answer") in (None, "", "-") and not question.get("answers"):
                state_label = "Chưa trả lời"
            else:
                state_label = "Sai"

            question_type = question.get("section_type")
            response_html = []
            if question_type == "g1":
                for option in question.get("options", []):
                    correct = bool(option.get("is_correct"))
                    selected = bool(option.get("is_selected"))
                    classes = ["option"]
                    if correct:
                        classes.append("correct")
                    if selected:
                        classes.append("selected")
                    marks = []
                    if correct:
                        marks.append(tag("Đáp án hệ thống", "system"))
                    if selected:
                        marks.append(tag("Học sinh chọn", "student"))
                    response_html.append(
                        f'<div class="{" ".join(classes)}">'
                        f'<span class="letter">{safe(option.get("label") or "")}</span>'
                        f'<div class="option-content">{content(option.get("content"))}</div>'
                        f'<div class="tags">{"".join(marks)}</div></div>'
                    )
                response = f'<div class="option-list">{"".join(response_html)}</div>'
            elif question_type == "g2":
                for option in question.get("options", []):
                    student_choice = question.get("student_tf_answers", {}).get(
                        str(option.get("id"))
                    )
                    expected = "true" if option.get("is_correct") else "false"
                    student_value = (
                        "Đúng" if student_choice in (True, "true")
                        else "Sai" if student_choice in (False, "false")
                        else "Chưa chọn"
                    )
                    response_html.append(
                        '<div class="tf-row">'
                        f'<div class="tf-statement"><strong>{safe(option.get("label") or "")})</strong> '
                        f'{content(option.get("content"))}</div>'
                        '<div class="tags">'
                        f'{tag("Đáp án: " + ("Đúng" if expected == "true" else "Sai"), "system")}'
                        f'{tag("Học sinh: " + student_value, "student")}'
                        '</div></div>'
                    )
                response = f'<div class="tf-list">{"".join(response_html)}</div>'
            elif question_type == "g3":
                correct_answer = question.get("correct_short_answer") or "Chưa cấu hình đáp án"
                student_answer = question.get("student_answer")
                response = '<div class="answer-grid">'
                response += answer_block("Đáp án hệ thống", correct_answer)
                response += answer_block(
                    "Học sinh trả lời",
                    student_answer if student_answer not in (None, "", "-") else "Chưa trả lời",
                    student_answer in (None, "", "-"),
                )
                response += "</div>"
            else:
                student_answer = question.get("student_answer")
                response = '<div class="answer-grid">'
                response += answer_block("Đáp án hệ thống", "Chấm tự luận thủ công")
                response += answer_block(
                    "Học sinh trả lời",
                    student_answer if student_answer not in (None, "", "-") else "Chưa trả lời",
                    student_answer in (None, "", "-"),
                )
                response += "</div>"

            points = (
                f'{earned:.2f} / {maximum:.2f} điểm'
                if is_graded else f'Chưa chấm / {maximum:.2f} điểm'
            )
            questions_html.append(
                '<article class="question">'
                '<div class="question-meta">'
                f'<strong>Câu {safe(question.get("number", "-"))}</strong>'
                f'<span>{safe(state_label)} · {safe(points)}</span>'
                '</div>'
                f'<div class="question-content">{content(question.get("content"))}</div>'
                '<div class="response-title">ĐÁP ÁN HỆ THỐNG VÀ CÂU TRẢ LỜI CỦA HỌC SINH</div>'
                f'{response}</article>'
            )
        rendered_sections.append(
            f'<section><h2>{safe(section.get("title"))}</h2>'
            f'{"".join(questions_html)}</section>'
        )

    return f"""<!doctype html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Phiếu Làm Bài Online - {safe(exam_title)}</title>
<script>
window.MathJax = {{
  tex: {{
    inlineMath: [['$', '$'], ['\\\\(', '\\\\)']],
    displayMath: [['$$', '$$'], ['\\\\[', '\\\\]']],
    processEscapes: true
  }},
  startup: {{typeset: false}},
  svg: {{fontCache: 'local'}}
}};
</script>
<script defer src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-svg.js"></script>
<style>
@page {{ size: A4; margin: 10mm; }}
* {{ box-sizing: border-box; }}
body {{ color: #172033; font: 10pt Arial, sans-serif; line-height: 1.15; }}
body:not([data-pdf-ready="true"]) {{ visibility: hidden; }}
.institution {{ display: grid; font-size: 9pt; font-weight: bold; grid-template-columns: 1fr 1.4fr; gap: 12px; text-align: center; }}
h1 {{ color: #17365d; font-size: 18pt; margin: 10px 0 2px; text-align: center; }}
.exam-title {{ font-size: 12pt; font-weight: bold; margin: 0 0 8px; text-align: center; }}
h2 {{ background: #eaf1f8; color: #17365d; font-size: 12pt; margin: 12px 0 6px; padding: 5px 8px; }}
.summary {{ border: 1px solid #d6deea; border-radius: 6px; display: grid; grid-template-columns: 1fr 1fr; gap: 4px 12px; margin-bottom: 10px; padding: 8px; }}
.question {{ border: 1px solid #d6deea; border-radius: 7px; break-inside: avoid; margin: 0 0 8px; padding: 8px; }}
.question-meta {{ align-items: center; border-bottom: 1px solid #e4e9f1; display: flex; justify-content: space-between; padding-bottom: 4px; }}
.question-content {{ margin: 6px 0; }}
.question-content p,.option-content p,.tf-statement p,.answer-content p {{ margin: 0; }}
.response-title {{ color: #315a82; font-size: 8pt; font-weight: bold; margin: 5px 0; }}
.option-list,.tf-list {{ display: grid; gap: 4px; }}
.option,.tf-row {{ align-items: center; border: 1px solid #d6deea; border-radius: 6px; display: flex; gap: 8px; padding: 5px 7px; }}
.option.correct {{ background: #effaf5; border-color: #51b88a; }}
.option.selected {{ border-width: 2px; }}
.letter {{ font-weight: bold; min-width: 18px; }}
.option-content,.tf-statement {{ flex: 1; min-width: 0; }}
.tags {{ display: flex; flex-wrap: wrap; gap: 3px; justify-content: flex-end; }}
.tag {{ border-radius: 10px; font-size: 8pt; font-weight: bold; padding: 2px 5px; white-space: nowrap; }}
.tag.system {{ background: #d9f4e7; color: #176b48; }}
.tag.student {{ background: #e2edff; color: #2456a6; }}
.answer-grid {{ display: grid; gap: 6px; grid-template-columns: 1fr 1fr; }}
.answer-content {{ border: 1px solid #d6deea; border-radius: 6px; margin-top: 3px; min-height: 28px; overflow-wrap: anywhere; padding: 6px; }}
.answer-content.empty {{ color: #737e90; font-style: italic; }}
.signature {{ align-items: baseline; break-inside: avoid; display: flex; font-size: 10pt; gap: 8px; grid-column: 1 / -1; justify-content: flex-end; margin: 0; padding-top: 4px; }}
.signature-line {{ border-bottom: 1px solid #172033; display: inline-block; height: 14px; width: 55mm; }}
img {{ max-width: 100%; }}
svg {{ max-width: 100%; }}
@media print {{ body {{ -webkit-print-color-adjust: exact; print-color-adjust: exact; }} }}
</style>
</head>
<body>
<header class="institution">
<div>SỞ GD&amp;ĐT TP CẦN THƠ</div>
<div>TRƯỜNG TIỂU HỌC, THCS VÀ THPT<br>QUỐC TẾ HÒA BÌNH</div>
</header>
<h1>PHIẾU LÀM BÀI ONLINE</h1>
<div class="exam-title">{safe(exam_title)}</div>
<div class="summary">
<div><strong>Học sinh:</strong> {safe(student_name)} ({safe(username)})</div>
<div><strong>Lớp:</strong> {safe(class_name or "-")}</div>
<div><strong>Điểm:</strong> {safe(score if score is not None else "-")} / {safe(total_score)}</div>
<div><strong>Thời gian nộp:</strong> {safe(submitted_at or "-")}</div>
<div><strong>Trạng thái:</strong> {safe(status_labels.get(status or "", status or "-"))}</div>
<div class="signature">
<strong>HS ký tên:</strong>
<span class="signature-line"></span>
</div>
</div>
{"".join(rendered_sections)}
<script>
window.addEventListener('load', async () => {{
  const markReady = message => {{
    if (message) {{
      const notice = document.createElement('p');
      notice.textContent = message;
      notice.style.cssText = 'background:#fff4d6;color:#805b00;padding:8px';
      document.body.insertBefore(notice, document.body.firstChild);
    }}
    document.body.dataset.pdfReady = 'true';
  }};
  if (window.MathJax) {{
    try {{
      await window.MathJax.startup.promise;
      await window.MathJax.typesetPromise();
      markReady();
    }} catch (error) {{
      markReady('Không thể kết xuất công thức bằng MathJax: ' + String(error));
    }}
  }} else {{
    markReady('Không tải được MathJax; công thức được giữ ở dạng LaTeX.');
  }}
}});
</script>
</body>
</html>"""


def _build_browser_pdf(html: str) -> Optional[bytes]:
    browser = _find_pdf_browser()
    if not browser:
        return None

    with tempfile.TemporaryDirectory(prefix="pisq-pdf-") as temp_dir:
        html_path = Path(temp_dir, "submission.html")
        pdf_path = Path(temp_dir, "submission.pdf")
        profile_path = Path(temp_dir, "browser-profile")
        html_path.write_text(html, encoding="utf-8")
        try:
            subprocess.run(
                [
                    browser,
                    "--headless",
                    "--disable-gpu",
                    "--no-first-run",
                    "--no-default-browser-check",
                    f"--user-data-dir={profile_path}",
                    "--virtual-time-budget=30000",
                    "--no-pdf-header-footer",
                    f"--print-to-pdf={pdf_path}",
                    html_path.as_uri(),
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                timeout=60,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("Quá thời gian chờ trình duyệt kết xuất PDF.") from exc
        except subprocess.CalledProcessError as exc:
            error = (exc.stderr or b"").decode("utf-8", errors="replace").strip()
            detail = f" Chi tiết: {error}" if error else ""
            raise RuntimeError(
                f"Trình duyệt không thể kết xuất PDF.{detail}"
            ) from exc
        except OSError as exc:
            raise RuntimeError(f"Không thể tạo PDF bằng trình duyệt: {exc}") from exc

        if not pdf_path.is_file():
            raise RuntimeError("Trình duyệt không tạo được file PDF.")
        return pdf_path.read_bytes()


def build_student_submission_pdf(
    exam_title: str,
    student_name: str,
    username: str,
    class_name: Optional[str],
    score: Any,
    total_score: Any,
    submitted_at: Any,
    sections: List[Dict[str, Any]],
    status: Optional[str] = None,
) -> bytes:
    browser_pdf = _build_browser_pdf(
        _comparison_html(
            exam_title,
            student_name,
            username,
            class_name,
            score,
            total_score,
            submitted_at,
            status,
            sections,
        )
    )
    if browser_pdf:
        return browser_pdf

    _register_vietnamese_font()

    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=10 * mm,
        leftMargin=10 * mm,
        topMargin=10 * mm,
        bottomMargin=10 * mm,
        title=f"Phiếu làm bài online - {exam_title}",
        author="PisQ",
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "PisQSubmissionTitle",
        parent=styles["Title"],
        fontName="PisQUnicode-Bold",
        fontSize=16,
        leading=18,
        alignment=1,
        textColor=colors.HexColor("#17365D"),
    )
    institution_style = ParagraphStyle(
        "PisQSubmissionInstitution",
        parent=styles["BodyText"],
        fontName="PisQUnicode-Bold",
        fontSize=9,
        leading=10,
        alignment=1,
        spaceBefore=0,
        spaceAfter=0,
    )
    body_style = ParagraphStyle(
        "PisQSubmissionBody",
        parent=styles["BodyText"],
        fontName="PisQUnicode",
        fontSize=10,
        leading=11,
        spaceBefore=0,
        spaceAfter=1,
    )
    exam_title_style = ParagraphStyle(
        "PisQSubmissionExamTitle",
        parent=body_style,
        fontName="PisQUnicode-Bold",
        fontSize=12,
        leading=13,
        alignment=1,
        spaceBefore=0,
        spaceAfter=3 * mm,
    )
    signature_label_style = ParagraphStyle(
        "PisQSubmissionSignatureLabel",
        parent=body_style,
        fontName="PisQUnicode-Bold",
        fontSize=10,
        leading=11,
        spaceBefore=0,
        spaceAfter=0,
    )
    section_style = ParagraphStyle(
        "PisQSubmissionSection",
        parent=body_style,
        fontName="PisQUnicode-Bold",
        fontSize=12,
        leading=13,
        textColor=colors.HexColor("#17365D"),
        backColor=colors.HexColor("#EAF1F8"),
        borderPadding=3,
        spaceBefore=2 * mm,
        spaceAfter=1 * mm,
    )
    question_style = ParagraphStyle(
        "PisQSubmissionQuestion",
        parent=body_style,
        fontName="PisQUnicode-Bold",
        textColor=colors.HexColor("#1F2937"),
        leading=11,
        spaceBefore=1 * mm,
        spaceAfter=0,
    )
    option_style = ParagraphStyle(
        "PisQSubmissionOption",
        parent=body_style,
        leftIndent=5 * mm,
        spaceBefore=0,
        spaceAfter=0,
    )
    detail_style = ParagraphStyle(
        "PisQSubmissionDetail",
        parent=body_style,
        leftIndent=5 * mm,
        textColor=colors.HexColor("#374151"),
        spaceBefore=0,
        spaceAfter=0,
    )

    story = [
        Paragraph(
            "SỞ GD&amp;ĐT TP CẦN THƠ<br/>"
            "TRƯỜNG TIỂU HỌC, THCS VÀ THPT<br/>"
            "QUỐC TẾ HÒA BÌNH",
            institution_style,
        ),
        Spacer(1, 2 * mm),
        Paragraph("PHIẾU LÀM BÀI ONLINE", title_style),
        Paragraph(escape(exam_title), exam_title_style),
        Table(
            [
                [
                    _paragraph(f"Học sinh: {student_name} ({username})", body_style),
                    _paragraph(f"Lớp: {class_name or '-'}", body_style),
                ],
                [
                    _paragraph(
                        f"Điểm: {score if score is not None else '-'} / {total_score}",
                        body_style,
                    ),
                    _paragraph(f"Thời gian nộp: {submitted_at or '-'}", body_style),
                ],
                [
                    _paragraph(f"Trạng thái: {status or '-'}", body_style),
                    "",
                ],
                [
                    "",
                    Table(
                        [[Paragraph("HS ký tên:", signature_label_style), ""]],
                        colWidths=[22 * mm, 55 * mm],
                        rowHeights=[8 * mm],
                        hAlign="RIGHT",
                        style=TableStyle([
                            ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
                            ("ALIGN", (0, 0), (0, 0), "RIGHT"),
                            ("LINEBELOW", (1, 0), (1, 0), 0.8, colors.HexColor("#172033")),
                            ("LEFTPADDING", (0, 0), (-1, -1), 2),
                            ("RIGHTPADDING", (0, 0), (-1, -1), 2),
                            ("TOPPADDING", (0, 0), (-1, -1), 0),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                        ]),
                    ),
                ],
            ],
            colWidths=[93 * mm, 93 * mm],
            hAlign="LEFT",
            style=TableStyle([
                ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#D6DEEA")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("ALIGN", (1, 3), (1, 3), "RIGHT"),
            ]),
        ),
        Spacer(1, 1 * mm),
    ]

    for section in sections:
        story.append(Paragraph(escape(_plain_text(section.get("title"))), section_style))
        for question in section.get("questions", []):
            earned = float(question.get("earned_points") or 0)
            maximum = float(question.get("possible_points") or 0)
            story.append(Paragraph(
                f"Câu {escape(str(question.get('number', '-')))}"
                f"&nbsp;&nbsp;·&nbsp;&nbsp;"
                f"{escape(str(question.get('earned_points', 0)))} / "
                f"{escape(str(question.get('possible_points', 0)))} điểm",
                question_style,
            ))
            story.append(Paragraph(_reportlab_markup(question.get("content")), body_style))
            story.append(Paragraph(
                "<b>ĐÁP ÁN HỆ THỐNG VÀ CÂU TRẢ LỜI CỦA HỌC SINH</b>",
                detail_style,
            ))
            if question.get("section_type") == "g1":
                for option in question.get("options", []):
                    label = escape(str(option.get("label") or ""))
                    marks = []
                    if option.get("is_correct"):
                        marks.append("Đáp án hệ thống")
                    if option.get("is_selected"):
                        marks.append("Học sinh chọn")
                    suffix = f" ({', '.join(marks)})" if marks else ""
                    story.append(Paragraph(
                        f"<b>{label})</b>&nbsp; "
                        f"{_reportlab_markup(option.get('content'))}"
                        f"{escape(suffix)}",
                        option_style,
                    ))
            elif question.get("section_type") == "g2":
                for option in question.get("options", []):
                    correct = bool(option.get("is_correct"))
                    selected = question.get("student_tf_answers", {}).get(
                        str(option.get("id"))
                    )
                    student_value = (
                        "Đúng" if selected in (True, "true")
                        else "Sai" if selected in (False, "false")
                        else "Chưa chọn"
                    )
                    story.append(Paragraph(
                        f"<b>{escape(str(option.get('label') or ''))})</b>&nbsp;"
                        f"{_reportlab_markup(option.get('content'))}"
                        f"&nbsp;&nbsp;Đáp án: {'Đúng' if correct else 'Sai'}"
                        f"&nbsp;&nbsp;Học sinh: {student_value}",
                        option_style,
                    ))
            else:
                correct_answer = question.get("correct_short_answer")
                if question.get("section_type") == "g4":
                    correct_answer = "Chấm tự luận thủ công"
                story.append(Paragraph(
                    f"<b>Đáp án hệ thống:</b>&nbsp;"
                    f"{_reportlab_markup(correct_answer or 'Chưa cấu hình đáp án')}",
                    detail_style,
                ))
                student_answer = question.get("student_answer")
                story.append(Paragraph(
                    f"<b>Học sinh trả lời:</b>&nbsp;"
                    f"{_reportlab_markup(student_answer or 'Chưa trả lời')}",
                    detail_style,
                ))
            story.append(Spacer(1, 1 * mm))

    document.build(story)
    return buffer.getvalue()
