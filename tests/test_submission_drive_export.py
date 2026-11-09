import json
import unittest
from unittest.mock import patch

import main
from google_drive import DriveConfigurationError


class FakeCursor:
    def __init__(self, submission=None, answers=None, counts=None):
        self.queries = []
        self.submission = submission
        self.answers = answers or []
        self.counts = counts
        self.current_query = ""

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, query, params=None):
        self.queries.append((query, params))
        self.current_query = query

    def fetchone(self):
        if "COUNT(DISTINCT q.id)" in self.current_query:
            return self.counts or {}
        if self.submission:
            return self.submission
        return {"id": 12, "exam_id": 7, "status": "in_progress"}

    def fetchall(self):
        if "FROM student_answers" in self.current_query:
            return self.answers
        return []


class FakeConnection:
    def __init__(self, submission=None, answers=None, counts=None):
        self.fake_cursor = FakeCursor(submission, answers, counts)
        self.committed = False
        self.closed = False

    def cursor(self):
        return self.fake_cursor

    def commit(self):
        self.committed = True

    def rollback(self):
        pass

    def close(self):
        self.closed = True


class SubmissionDriveExportTests(unittest.TestCase):
    def test_pdf_filename_uses_class_exam_username_ascii_and_three_digit_suffix(self):
        submission = {
            "class_name": "Lớp 12A1",
            "exam_title": "Kiểm tra Toán lớp 12",
            "username": "nguyenvanan",
        }

        with patch("main.secrets.randbelow", return_value=7):
            filename = main._submission_pdf_filename(submission)

        self.assertEqual(
            filename,
            "Lop 12A1_Kiem tra Toan lop 12_nguyenvanan_007.pdf",
        )
        self.assertTrue(filename.isascii())

    def test_duplicate_submit_returns_complete_result_without_reuploading_pdf(self):
        cursor = FakeCursor(
            submission={
                "id": 12,
                "exam_id": 7,
                "status": "graded",
                "score": 0,
            },
            counts={"correct_questions": 0, "total_questions": 22},
        )
        connection = FakeConnection()
        connection.fake_cursor = cursor

        with patch("main.get_db", return_value=connection), patch(
            "main.upload_student_submission"
        ) as upload_submission:
            result = main.submit_exam(12)

        self.assertEqual(result["status"], "already_submitted")
        self.assertEqual(result["score"], 0)
        self.assertEqual(result["correct_questions"], 0)
        self.assertEqual(result["total_questions"], 22)
        self.assertFalse(connection.committed)
        self.assertTrue(connection.closed)
        upload_submission.assert_not_called()

    def test_pdf_contains_only_the_selected_student_submission(self):
        submission = {
            "id": 12,
            "student_id": 3,
            "status": "graded",
            "score": 2.5,
            "submitted_at": "2026-11-05 10:00:00",
            "shuffled_data": json.dumps([
                {
                    "section_type": "g1",
                    "title": "Phần I",
                    "questions": [
                        {
                            "id": 42,
                            "number": 1,
                            "content": "Câu hỏi",
                            "points": 3,
                            "options": [
                                {"id": 77, "label": "B", "content": "Đáp án đã chọn"},
                                {
                                    "id": 78,
                                    "label": "A",
                                    "content": "<p>Lựa chọn khác</p>",
                                    "is_correct": True,
                                },
                            ],
                        },
                    ],
                },
            ]),
            "full_name": "Nguyễn Văn An",
            "username": "nguyenvanan",
            "class_name": "12A1",
            "exam_title": "Bài kiểm tra",
            "total_score": 10,
        }
        connection = FakeConnection(
            submission,
            [{
                "question_id": 42,
                "selected_option_id": 77,
                "text_answer": None,
                "essay_file_url": None,
                "awarded_points": 2.5,
            }],
        )

        with patch("main.get_db", return_value=connection), patch(
            "main.build_student_submission_pdf", return_value=b"%PDF-test"
        ) as build_pdf:
            pdf_bytes, result_submission = main.build_student_submission_export(12)

        self.assertEqual(pdf_bytes, b"%PDF-test")
        self.assertEqual(result_submission["id"], 12)
        exported_sections = build_pdf.call_args.args[-2]
        exported_question = exported_sections[0]["questions"][0]
        self.assertEqual(exported_question["section_type"], "g1")
        self.assertEqual(exported_question["student_answer"], "B. Đáp án đã chọn")
        self.assertEqual(exported_question["options"], [
            {
                "id": 77,
                "label": "B",
                "content": "Đáp án đã chọn",
                "is_correct": False,
                "is_selected": True,
            },
            {
                "id": 78,
                "label": "A",
                "content": "<p>Lựa chọn khác</p>",
                "is_correct": True,
                "is_selected": False,
            },
        ])
        self.assertEqual(exported_question["earned_points"], 2.5)
        self.assertEqual(build_pdf.call_args.args[-1], "graded")
        self.assertTrue(connection.closed)

    def test_submit_queues_pdf_upload_after_submission_is_committed(self):
        connection = FakeConnection()

        def upload_submission(submission_id):
            self.assertTrue(connection.committed)
            self.assertEqual(submission_id, 12)
            return {"status": "uploaded", "file": {"web_view_link": "https://drive.google.com"}}

        with patch("main.get_db", return_value=connection), patch(
            "main.upload_student_submission", side_effect=upload_submission
        ) as upload:
            result = main.submit_exam(12)

        self.assertEqual(result["drive_upload"]["status"], "pending")
        self.assertTrue(connection.closed)
        upload.assert_not_called()
        self.assertTrue(any(
            "drive_upload_status = 'pending'" in query
            for query, _params in connection.fake_cursor.queries
        ))

    def test_submit_bulk_loads_options_and_preserves_scoring(self):
        class ScoringCursor(FakeCursor):
            def __init__(self):
                super().__init__()
                self.batch_updates = []

            def fetchone(self):
                if "FROM exam_submissions" in self.current_query:
                    return {"id": 12, "exam_id": 7, "status": "in_progress"}
                return {}

            def fetchall(self):
                if "SELECT q.id as question_id" in self.current_query:
                    return [
                        {"question_id": 42, "question_points": 5, "section_type": "g1"},
                        {"question_id": 43, "question_points": 5, "section_type": "g1"},
                    ]
                if "FROM student_answers" in self.current_query:
                    return [
                        {"id": 1, "question_id": 42, "selected_option_id": 10, "text_answer": None},
                        {"id": 2, "question_id": 43, "selected_option_id": 20, "text_answer": None},
                    ]
                if "FROM question_options" in self.current_query:
                    return [
                        {"question_id": 42, "id": 10, "is_correct": 1, "content": "Correct"},
                        {"question_id": 42, "id": 11, "is_correct": 0, "content": "Incorrect"},
                        {"question_id": 43, "id": 20, "is_correct": 0, "content": "Incorrect"},
                        {"question_id": 43, "id": 21, "is_correct": 1, "content": "Correct"},
                    ]
                return []

            def executemany(self, query, values):
                self.batch_updates.append((query, values))

        connection = FakeConnection()
        cursor = ScoringCursor()
        connection.fake_cursor = cursor

        with patch("main.get_db", return_value=connection):
            result = main.submit_exam(12)

        self.assertEqual(result["score"], 5)
        self.assertEqual(result["correct_questions"], 1)
        options_queries = [
            query for query, _params in cursor.queries
            if "FROM question_options" in query
        ]
        self.assertEqual(len(options_queries), 1)
        self.assertEqual(
            cursor.batch_updates[0][1],
            [(1, 5, 1), (0, 0, 2)],
        )

    def test_drive_upload_retries_and_persists_success(self):
        uploaded = {
            "status": "uploaded",
            "file": {
                "id": "drive-file-1",
                "web_view_link": "https://drive.google.com/file/d/drive-file-1/view",
            },
        }
        with patch(
            "main.upload_student_submission",
            side_effect=[
                {"status": "failed", "detail": "Temporary failure"},
                uploaded,
            ],
        ) as upload_submission, patch(
            "main._set_submission_drive_upload_status"
        ) as save_status, patch("main.time.sleep"):
            main.process_submission_drive_upload(12)

        self.assertEqual(upload_submission.call_count, 2)
        self.assertEqual(save_status.call_args.args[:2], (12, "uploaded"))
        self.assertEqual(save_status.call_args.kwargs["file_id"], "drive-file-1")

    def test_drive_upload_marks_failed_after_three_attempts(self):
        with patch(
            "main.upload_student_submission",
            return_value={"status": "failed", "detail": "Drive unavailable"},
        ) as upload_submission, patch(
            "main._set_submission_drive_upload_status"
        ) as save_status, patch("main.time.sleep"):
            main.process_submission_drive_upload(12)

        self.assertEqual(upload_submission.call_count, 3)
        self.assertEqual(save_status.call_args.args[:2], (12, "failed"))
        self.assertEqual(save_status.call_args.kwargs["detail"], "Drive unavailable")

    def test_drive_failure_is_reported_without_reversing_submission(self):
        with patch(
            "main.build_student_submission_export",
            return_value=(
                b"%PDF-test",
                {
                    "username": "nva",
                    "student_id": 3,
                    "class_name": "12A1",
                    "exam_title": "Bài kiểm tra",
                },
            ),
        ), patch(
            "main.upload_pdf_to_drive",
            side_effect=DriveConfigurationError("Thiếu thông tin xác thực"),
        ) as upload_pdf, patch("main.secrets.randbelow", return_value=123):
            result = main.upload_student_submission(12)

        self.assertEqual(result, {
            "status": "failed",
            "detail": "Thiếu thông tin xác thực",
        })
        upload_pdf.assert_called_once_with(
            b"%PDF-test",
            "12A1_Bai kiem tra_nva_123.pdf",
        )


if __name__ == "__main__":
    unittest.main()
