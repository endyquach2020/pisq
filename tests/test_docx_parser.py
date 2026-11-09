import os
import tempfile
import unittest
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import patch

from docx import Document
from docx.oxml import parse_xml
from PIL import Image

from docx_parser import (
    _convert_mathtype_to_latex,
    _enhance_math_alpha,
    parse_paragraph_to_html,
    parse_docx_file,
)


class DocxParserMathTests(unittest.TestCase):
    def test_short_answer_accepts_da_colon_prefix(self):
        document = Document()
        document.add_paragraph("<#g3> Phần I. TỰ LUẬN - bài luyện tập")
        document.add_paragraph("Câu 1. Nhập kết quả:")
        document.add_paragraph("DA: 12")

        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as docx_file:
            path = docx_file.name
        try:
            document.save(path)
            sections = parse_docx_file(path)
        finally:
            os.remove(path)

        self.assertEqual(sections[0]["section_type"], "g3")
        self.assertEqual(sections[0]["title"], "Phần I. TỰ LUẬN - bài luyện tập")
        self.assertEqual(sections[0]["questions"][0]["short_answer"], "12")

    def test_short_answer_accepts_da_period_prefix(self):
        document = Document()
        document.add_paragraph("<#g3> Trả lời ngắn")
        document.add_paragraph("Câu 1. Tính kết quả:")
        document.add_paragraph("DA. 12")

        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as docx_file:
            path = docx_file.name
        try:
            document.save(path)
            sections = parse_docx_file(path)
        finally:
            os.remove(path)

        self.assertEqual(sections[0]["questions"][0]["short_answer"], "12")

    def test_short_answer_requires_da_punctuation(self):
        for answer_line in ("DA 12", "Đáp án: 12", "Answer: 12"):
            with self.subTest(answer_line=answer_line):
                document = Document()
                document.add_paragraph("<#g3> Trả lời ngắn")
                document.add_paragraph("Câu 1. Tính kết quả:")
                document.add_paragraph(answer_line)

                with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as docx_file:
                    path = docx_file.name
                try:
                    document.save(path)
                    with self.assertRaisesRegex(ValueError, "tiền tố bắt buộc 'DA\\.' hoặc 'DA:'"):
                        parse_docx_file(path)
                finally:
                    os.remove(path)

    def test_g4_tag_keeps_subquestions_as_essay_options(self):
        document = Document()
        document.add_paragraph("<#g4> Bài luyện tập chương lượng giác")
        document.add_paragraph("Câu 2. Giải các phương trình sau:")
        document.add_paragraph("a) Phương trình thứ nhất")
        document.add_paragraph("b) Phương trình thứ hai")

        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as docx_file:
            path = docx_file.name
        try:
            document.save(path)
            sections = parse_docx_file(path)
        finally:
            os.remove(path)

        self.assertEqual(sections[0]["section_type"], "g4")
        self.assertEqual(
            [(option["label"], option["content"]) for option in sections[0]["questions"][0]["options"]],
            [("a", "Phương trình thứ nhất"), ("b", "Phương trình thứ hai")],
        )

    def test_section_tag_wins_over_part_number_in_title(self):
        document = Document()
        document.add_paragraph("<#g3> PHẦN I. Trắc nghiệm nhiều lựa chọn")
        document.add_paragraph("Câu 1: Chọn đáp án đúng")
        document.add_paragraph("A. Phương án A")
        document.add_paragraph("B. Phương án B")

        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as docx_file:
            path = docx_file.name
        try:
            document.save(path)
            sections = parse_docx_file(path)
        finally:
            os.remove(path)

        self.assertEqual(sections[0]["section_type"], "g3")
        self.assertEqual(len(sections[0]["questions"][0]["options"]), 2)

    def test_g3_section_with_complete_underlined_multiple_choice_options_is_g1(self):
        document = Document()
        document.add_paragraph("<#g3> Phần I. Trắc nghiệm nhiều phương án lựa chọn")
        document.add_paragraph("Câu 1. Chọn đáp án đúng.")
        correct_option = document.add_paragraph()
        correct_option.add_run("A. Đáp án đúng").underline = True
        document.add_paragraph("B. Đáp án sai")
        document.add_paragraph("C. Đáp án sai")
        document.add_paragraph("D. Đáp án sai")

        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as docx_file:
            path = docx_file.name
        try:
            document.save(path)
            sections = parse_docx_file(path)
        finally:
            os.remove(path)

        self.assertEqual(sections[0]["section_type"], "g1")
        self.assertEqual(
            [option["label"] for option in sections[0]["questions"][0]["options"]],
            ["A", "B", "C", "D"],
        )

    def test_question_without_section_tag_is_rejected(self):
        document = Document()
        document.add_paragraph("Câu 1. Chọn đáp án đúng")

        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as docx_file:
            path = docx_file.name
        try:
            document.save(path)
            with self.assertRaisesRegex(ValueError, "thẻ <#g1>"):
                parse_docx_file(path)
        finally:
            os.remove(path)

    def test_skips_mathtype_conversion_when_document_has_no_ole_equations(self):
        document = Document()
        document.add_paragraph("No MathType equation")

        with patch("docx_parser.subprocess.run") as run:
            self.assertIsNone(_convert_mathtype_to_latex("unused.docx", document))

        run.assert_not_called()

    def test_enhances_antialiased_math_strokes(self):
        alpha = Image.new("L", (3, 1))
        alpha.putdata([0, 64, 255])

        enhanced = _enhance_math_alpha(alpha)

        self.assertEqual(enhanced.getpixel((0, 0)), 0)
        self.assertGreater(enhanced.getpixel((1, 0)), 64)
        self.assertEqual(enhanced.getpixel((2, 0)), 255)

    def test_converts_inline_omml_vector_to_latex(self):
        document = Document()
        paragraph = document.add_paragraph("Cho vectơ ")
        paragraph._p.append(parse_xml(
            '<m:oMath xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math">'
            '<m:acc><m:accPr><m:chr m:val="&#x20D7;"/></m:accPr>'
            '<m:e><m:r><m:t>u</m:t></m:r></m:e></m:acc></m:oMath>'
        ))

        content, _ = parse_paragraph_to_html(paragraph, document)

        self.assertIn(r"$\vec{u}$", content)

    def test_extracts_and_converts_legacy_vml_equation_in_paragraph(self):
        image_buffer = BytesIO()
        Image.new("RGB", (1, 1), color="white").save(image_buffer, format="PNG")
        image_bytes = image_buffer.getvalue()
        image_part = SimpleNamespace(blob=image_bytes, content_type="image/x-wmf")
        document = SimpleNamespace(
            part=SimpleNamespace(related_parts={"rId1": image_part})
        )
        paragraph_doc = Document()
        paragraph = paragraph_doc.add_paragraph()
        paragraph._p.append(parse_xml(
            '<w:r xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
            'xmlns:v="urn:schemas-microsoft-com:vml" '
            'xmlns:o="urn:schemas-microsoft-com:office:office" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            '<w:t>Before </w:t><w:object><v:shape style="width:30pt;height:16.2pt" '
            'o:ole=""><v:imagedata r:id="rId1"/></v:shape></w:object>'
            '<w:t> after</w:t></w:r>'
        ))

        with tempfile.TemporaryDirectory() as upload_dir:
            with patch("docx_parser.UPLOAD_DIR", upload_dir):
                content, _ = parse_paragraph_to_html(paragraph, document)

            self.assertIn("Before ", content)
            self.assertIn(" after", content)
            self.assertIn('class="inline-math-img" style="width:30pt;height:16.2pt"', content)
            image_url = content.split('src="', 1)[1].split('"', 1)[0]
            image_path = os.path.join(upload_dir, os.path.basename(image_url))
            with open(image_path, "rb") as image_file:
                self.assertEqual(image_file.read()[:8], b"\x89PNG\r\n\x1a\n")

    def test_rasterizes_wmf_equation_at_high_resolution(self):
        image_buffer = BytesIO()
        source_image = Image.new("RGB", (20, 15), color="white")
        source_image.putpixel((10, 7), (0, 0, 0))
        source_image.save(image_buffer, format="PNG")
        image_part = SimpleNamespace(blob=image_buffer.getvalue(), content_type="image/x-wmf")
        document = SimpleNamespace(
            part=SimpleNamespace(related_parts={"rId1": image_part})
        )
        paragraph_doc = Document()
        paragraph = paragraph_doc.add_paragraph()
        paragraph._p.append(parse_xml(
            '<w:r xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
            'xmlns:v="urn:schemas-microsoft-com:vml" '
            'xmlns:o="urn:schemas-microsoft-com:office:office" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            '<w:object><v:shape style="width:30pt;height:16.2pt" o:ole="">'
            '<v:imagedata r:id="rId1"/></v:shape></w:object></w:r>'
        ))

        class FakeMetafile:
            format = "WMF"
            dpi = None
            size = (120, 90)

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def load(self, dpi=None):
                self.dpi = dpi
                self.format = None

            def convert(self, mode):
                self.output = Image.new(mode, self.size, color="white")
                self.output.putpixel((60, 42), (0, 0, 0))
                return self.output

        metafile = FakeMetafile()
        with tempfile.TemporaryDirectory() as upload_dir:
            with patch("PIL.Image.open", return_value=metafile):
                with patch("docx_parser.UPLOAD_DIR", upload_dir):
                    content, _ = parse_paragraph_to_html(paragraph, document)

            self.assertIn("inline-math-img", content)
            self.assertEqual(metafile.dpi, 300)
            image_url = content.split('src="', 1)[1].split('"', 1)[0]
            image_path = os.path.join(upload_dir, os.path.basename(image_url))
            with Image.open(image_path) as rendered:
                self.assertEqual(rendered.size, (120, 90))
                self.assertEqual(rendered.getpixel((0, 0)), (255, 255, 255, 0))
                self.assertEqual(rendered.getpixel((60, 42)), (255, 255, 255, 255))

    def test_prefers_word_rendered_equation_over_vml_preview(self):
        preview = BytesIO()
        Image.new("RGB", (1, 1), color="black").save(preview, format="PNG")
        rendered = Image.new("RGB", (5, 5), color="white")
        rendered.putpixel((2, 2), (0, 0, 0))
        rendered_buffer = BytesIO()
        rendered.save(rendered_buffer, format="PNG")
        image_part = SimpleNamespace(
            blob=preview.getvalue(),
            content_type="image/x-wmf",
        )
        document = SimpleNamespace(
            part=SimpleNamespace(related_parts={"rId1": image_part})
        )
        paragraph_doc = Document()
        paragraph = paragraph_doc.add_paragraph()
        paragraph._p.append(parse_xml(
            '<w:r xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
            'xmlns:v="urn:schemas-microsoft-com:vml" '
            'xmlns:o="urn:schemas-microsoft-com:office:office" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            '<w:object><v:shape style="width:30pt;height:16.2pt" o:ole="">'
            '<v:imagedata r:id="rId1"/></v:shape></w:object></w:r>'
        ))

        with tempfile.TemporaryDirectory() as upload_dir:
            with patch("docx_parser.UPLOAD_DIR", upload_dir):
                content, _ = parse_paragraph_to_html(
                    paragraph,
                    document,
                    {"rId1": rendered_buffer.getvalue()},
                )

            image_url = content.split('src="', 1)[1].split('"', 1)[0]
            image_path = os.path.join(upload_dir, os.path.basename(image_url))
            with Image.open(image_path) as equation:
                self.assertEqual(equation.mode, "RGBA")
                self.assertEqual(equation.getpixel((0, 0)), (255, 255, 255, 0))
                self.assertEqual(equation.getpixel((2, 2)), (255, 255, 255, 255))


if __name__ == "__main__":
    unittest.main()
