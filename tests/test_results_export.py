import base64
import json
import os
import unittest
from io import BytesIO
from unittest.mock import patch

from google_drive import (
    DEFAULT_DRIVE_FOLDER_ID,
    DriveConfigurationError,
    DriveUploadError,
    upload_pdf_to_drive,
)
from results_export import _comparison_html, _reportlab_markup, build_student_submission_pdf


class ResultsExportTests(unittest.TestCase):
    def test_comparison_pdf_html_preserves_math_and_answer_marks(self):
        html = _comparison_html(
            "Kiểm tra Toán",
            "Nguyễn Văn An",
            "nva",
            "12A1",
            1,
            2,
            "2026-11-05 10:00:00",
            "graded",
            [
                {
                    "title": "Phần I",
                    "section_type": "g1",
                    "questions": [
                        {
                            "section_type": "g1",
                            "number": 1,
                            "content": "<p>Tính $x^2$</p>",
                            "options": [
                                {
                                    "label": "A",
                                    "content": "Đúng",
                                    "is_correct": True,
                                    "is_selected": False,
                                },
                                {
                                    "label": "B",
                                    "content": "Sai",
                                    "is_correct": False,
                                    "is_selected": True,
                                },
                            ],
                            "earned_points": 0,
                            "possible_points": 1,
                        }
                    ],
                }
            ],
        )

        self.assertIn("tex-svg.js", html)
        self.assertIn("$x^2$", html)
        self.assertIn("Đáp án hệ thống", html)
        self.assertIn("Học sinh chọn", html)
        self.assertIn("PHIẾU LÀM BÀI ONLINE", html)
        self.assertNotIn("<h1>Đối Chiếu Bài Làm</h1>", html)
        self.assertIn("SỞ GD&amp;ĐT TP CẦN THƠ", html)
        self.assertIn("TRƯỜNG TIỂU HỌC, THCS VÀ THPT<br>QUỐC TẾ HÒA BÌNH", html)
        self.assertIn('<div class="exam-title">Kiểm tra Toán</div>', html)
        self.assertIn("<strong>HS ký tên:</strong>", html)
        self.assertIn('class="signature-line"', html)
        self.assertLess(html.index('<div class="summary">'), html.index('class="signature"'))
        self.assertIn(
            '<span class="signature-line"></span>\n</div>\n</div>\n<section>',
            html,
        )
        self.assertIn("font-size: 10pt", html)
        self.assertIn("line-height: 1.15", html)
        self.assertIn("@page { size: A4; margin: 10mm; }", html)
        self.assertIn("margin: 0 0 8px; padding: 8px", html)
        self.assertNotIn("signature-space", html)

    def test_builds_pdf_with_unicode_student_submission(self):
        pdf_bytes = build_student_submission_pdf(
            "Kiểm tra Toán lớp 12",
            "Nguyễn Văn Ánh",
            "nva",
            "12A1",
            8.5,
            10,
            "2026-11-05 10:00:00",
            [
                {
                    "title": "PHẦN I. Trắc nghiệm",
                    "section_type": "g1",
                    "questions": [
                        {
                            "number": 1,
                            "content": "<p>Chọn đáp án đúng</p>",
                            "student_answer": "A. Đáp án mẫu",
                            "options": [
                                {"label": "A", "content": "<b>Đáp án mẫu</b>"},
                                {"label": "B", "content": "Lựa chọn khác"},
                            ],
                            "earned_points": 1,
                            "possible_points": 1,
                            "answers": [],
                        }
                    ],
                },
            ],
        )

        self.assertTrue(pdf_bytes.startswith(b"%PDF-"))
        self.assertGreater(len(pdf_bytes), 1000)

    def test_builds_fallback_pdf_when_no_browser_is_available(self):
        with patch("results_export._build_browser_pdf", return_value=None):
            pdf_bytes = build_student_submission_pdf(
                "Kiểm tra Toán",
                "Nguyễn Văn An",
                "nva",
                "12A1",
                1,
                1,
                "2026-11-05 10:00:00",
                [
                    {
                        "title": "Phần I",
                        "section_type": "g1",
                        "questions": [
                            {
                                "section_type": "g1",
                                "number": 1,
                                "content": "Câu hỏi",
                                "options": [
                                    {
                                        "label": "A",
                                        "content": "Đúng",
                                        "is_correct": True,
                                        "is_selected": True,
                                    }
                                ],
                                "earned_points": 1,
                                "possible_points": 1,
                            }
                        ],
                    }
                ],
                "graded",
            )

        self.assertTrue(pdf_bytes.startswith(b"%PDF-"))
        self.assertGreater(len(pdf_bytes), 1000)

    def test_reportlab_markup_preserves_formatting_equations_and_image_fallback(self):
        markup = _reportlab_markup(
            '<p><strong>Nội dung</strong> $x_1$ '
            '<img src="/static/uploads/not-found.png" alt="Hình minh họa"></p>'
        )

        self.assertIn("<b>Nội dung</b>", markup)
        self.assertIn("$x_1$", markup)
        self.assertIn("[Không tìm thấy hình: Hình minh họa]", markup)

    def test_missing_apps_script_configuration_is_reported(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(DriveConfigurationError):
                upload_pdf_to_drive(b"%PDF", "results.pdf")

    def test_uploads_pdf_to_apps_script_and_uses_configured_folder(self):
        response = BytesIO(b"""{
            "status":"success",
            "file":{
                "id":"uploaded-file-id",
                "name":"results.pdf",
                "webViewLink":"https://drive.google.com/file/d/uploaded-file-id/view"
            }
        }""")
        with patch.dict(os.environ, {
            "GOOGLE_APPS_SCRIPT_URL": "https://script.google.com/macros/s/test/exec",
            "GOOGLE_APPS_SCRIPT_TOKEN": "test-secret",
        }, clear=True), patch("google_drive.urlopen", return_value=response) as urlopen_mock:
            result = upload_pdf_to_drive(b"%PDF-test", "results.pdf")

        request = urlopen_mock.call_args.args[0]
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(DEFAULT_DRIVE_FOLDER_ID, "1n4KAU_hVz-0TrhFBY_1BHU7qrsQsJ701")
        self.assertEqual(payload["token"], "test-secret")
        self.assertEqual(payload["fileName"], "results.pdf")
        self.assertEqual(base64.b64decode(payload["fileData"]), b"%PDF-test")
        self.assertEqual(payload["folderId"], DEFAULT_DRIVE_FOLDER_ID)
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(result["id"], "uploaded-file-id")
        self.assertEqual(
            result["web_view_link"],
            "https://drive.google.com/file/d/uploaded-file-id/view",
        )

    def test_apps_script_error_is_reported(self):
        response = BytesIO(b'{"status":"error","message":"Invalid token"}')
        with patch.dict(os.environ, {
            "GOOGLE_APPS_SCRIPT_URL": "https://script.google.com/macros/s/test/exec",
            "GOOGLE_APPS_SCRIPT_TOKEN": "test-secret",
        }, clear=True), patch("google_drive.urlopen", return_value=response):
            with self.assertRaisesRegex(DriveUploadError, "Invalid token"):
                upload_pdf_to_drive(b"%PDF-test", "results.pdf")


if __name__ == "__main__":
    unittest.main()
