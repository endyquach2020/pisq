import os
import json
import unittest
from unittest.mock import patch

import main


class FakeCursor:
    def __init__(self, *, rows=None, row=None):
        self.rows = rows or []
        self.row = row
        self.queries = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, query, params=None):
        self.queries.append((query, params))

    def fetchall(self):
        return self.rows

    def fetchone(self):
        if isinstance(self.row, list):
            return self.row.pop(0)
        return self.row


class RetakeCursor(FakeCursor):
    def fetchall(self):
        return []


class FakeConnection:
    def __init__(self, cursor):
        self.fake_cursor = cursor
        self.closed = False
        self.committed = False

    def cursor(self):
        return self.fake_cursor

    def close(self):
        self.closed = True

    def rollback(self):
        pass

    def commit(self):
        self.committed = True


class ResumableExamCursor(FakeCursor):
    def __init__(self, row, section_types, saved_answers):
        super().__init__(row=row)
        self.section_types = section_types
        self.saved_answers = saved_answers

    def fetchall(self):
        query = self.queries[-1][0]
        if "FROM exam_sections" in query:
            return self.section_types
        if "FROM student_answers" in query:
            return self.saved_answers
        return []

class StudentSubmissionReviewCursor(FakeCursor):
    def __init__(self, submission, answers):
        super().__init__(row=submission)
        self.answers = answers

    def fetchall(self):
        if "FROM student_answers" in self.queries[-1][0]:
            return self.answers
        return []


class SubmissionReviewCursor(FakeCursor):
    def __init__(self, submission, answers, option_rows):
        super().__init__(row=submission)
        self.answers = answers
        self.option_rows = option_rows

    def fetchall(self):
        query = self.queries[-1][0]
        if "FROM student_answers sa" in query:
            return self.answers
        if "FROM question_options" in query:
            return self.option_rows
        return []


class StudentExamStatusTests(unittest.TestCase):
    def test_student_exam_list_is_filtered_for_student(self):
        cursor = FakeCursor(rows=[{
            "id": 4,
            "student_status": "graded",
            "student_score": 8.5,
        }])
        connection = FakeConnection(cursor)

        with patch("main.get_db", return_value=connection):
            result = main.get_student_exams(student_id=23)

        self.assertEqual(result["exams"][0]["student_status"], "graded")
        query, params = cursor.queries[0]
        self.assertIn("latest.student_id = student.id", query)
        self.assertIn("e.class_id = student.class_id", query)
        self.assertEqual(params, (23,))
        self.assertTrue(connection.closed)

    def test_completed_exam_cannot_be_started_again(self):
        for status in ("submitted", "graded", "timed_out"):
            with self.subTest(status=status):
                cursor = RetakeCursor(row=[
                    {"class_id": 4},
                    {"class_id": 4},
                    {"id": 51, "status": status, "score": 7.5},
                ])
                connection = FakeConnection(cursor)

                with patch("main.get_db", return_value=connection), patch.dict(
                    os.environ, {"ALLOW_MULTIPLE_EXAM_ATTEMPTS": "false"}
                ):
                    result = main.start_exam(exam_id=9, student_id=23)

                self.assertEqual(result["status"], "already_submitted")
                self.assertEqual(result["score"], 7.5)
                self.assertEqual(len(cursor.queries), 3)
                self.assertTrue(connection.closed)

    def test_completed_exam_can_be_restarted_when_multiple_attempts_are_enabled(self):
        cursor = FakeCursor(row=[
            {"class_id": 4},
            {"class_id": 4},
            {"id": 51, "status": "graded", "score": 7.5},
            {"title": "Exam", "duration_minutes": 45},
        ])
        cursor.lastrowid = 52
        connection = FakeConnection(cursor)

        with patch("main.get_db", return_value=connection), patch.dict(
            os.environ, {"ALLOW_MULTIPLE_EXAM_ATTEMPTS": "true"}
        ):
            result = main.start_exam(exam_id=9, student_id=23)

        self.assertEqual(result["status"], "started")
        self.assertEqual(result["submission_id"], 52)
        insert_query = next(
            query for query, _ in cursor.queries
            if "INSERT INTO exam_submissions" in query
        )
        self.assertIn("VALUES (%s, %s, %s, 'in_progress', %s)", insert_query)
        self.assertTrue(connection.committed)
        self.assertTrue(connection.closed)

    def test_resuming_exam_uses_section_type_from_tagged_exam_section(self):
        stale_shuffled_data = [{
            "id": 31,
            "section_type": "g3",
            "title": "User-defined title",
            "questions": [{
                "id": 41,
                "options": [
                    {"id": 51, "label": "A", "content": "equation-a"},
                    {"id": 52, "label": "B", "content": "equation-b"},
                ],
            }],
        }]
        cursor = ResumableExamCursor(
            row=[
                {"class_id": 4},
                {"class_id": 4},
                {
                    "id": 61,
                    "status": "in_progress",
                    "shuffled_data": json.dumps(stale_shuffled_data),
                    "start_time": "2026-11-04 10:00:00",
                },
                {"title": "Exam", "duration_minutes": 45},
            ],
            section_types=[{"id": 31, "section_type": "g4"}],
            saved_answers=[],
        )
        connection = FakeConnection(cursor)

        with patch("main.get_db", return_value=connection):
            result = main.start_exam(exam_id=9, student_id=23)

        resumed_section = result["shuffled_exam"][0]
        self.assertEqual(resumed_section["section_type"], "g4")
        self.assertEqual(
            [option["label"] for option in resumed_section["questions"][0]["options"]],
            ["a", "b"],
        )
        self.assertEqual(
            [option["content"] for option in resumed_section["questions"][0]["options"]],
            ["equation-a", "equation-b"],
        )
        self.assertTrue(connection.committed)
        self.assertTrue(any("UPDATE exam_submissions SET shuffled_data" in query for query, _ in cursor.queries))
        self.assertTrue(connection.closed)

    def test_student_cannot_start_exam_assigned_to_another_class(self):
        cursor = FakeCursor(row=[
            {"class_id": 4},
            {"class_id": 5},
        ])
        connection = FakeConnection(cursor)

        with patch("main.get_db", return_value=connection):
            with self.assertRaises(main.HTTPException) as error:
                main.start_exam(exam_id=9, student_id=23)

        self.assertEqual(error.exception.status_code, 403)
        self.assertEqual(len(cursor.queries), 2)
        self.assertTrue(connection.closed)

    def test_student_review_shows_awarded_and_possible_points(self):
        submission = {
            "id": 88,
            "student_id": 23,
            "status": "graded",
            "score": 1,
            "exam_title": "Bài kiểm tra",
            "total_score": 10,
            "shuffled_data": json.dumps([{
                "id": 2,
                "section_type": "g1",
                "title": "Phần I",
                "questions": [{
                    "id": 10,
                    "number": 1,
                    "content": "Câu hỏi",
                    "points": 1,
                    "options": [
                        {"id": 20, "label": "A", "content": "Phương án A"},
                        {"id": 21, "label": "B", "content": "Phương án B"},
                    ],
                }, {
                    "id": 11,
                    "number": 2,
                    "content": "Câu hỏi 2",
                    "points": 1,
                    "options": [],
                }, {
                    "id": 13,
                    "number": 3,
                    "content": "Câu chưa trả lời",
                    "points": 0.5,
                    "options": [],
                }],
            }, {
                "id": 3,
                "section_type": "g3",
                "title": "Phần III",
                "questions": [{
                    "id": 12,
                    "number": 3,
                    "content": "Câu trả lời ngắn",
                    "points": 1,
                    "options": [
                        {"id": 22, "label": "ANS", "content": "Đáp án bí mật"},
                    ],
                }],
            }, {
                "id": 4,
                "section_type": "g2",
                "title": "Phần II",
                "questions": [{
                    "id": 14,
                    "number": 4,
                    "content": "Câu đúng sai",
                    "points": 1,
                    "options": [],
                }],
            }]),
        }
        cursor = StudentSubmissionReviewCursor(submission, [
            {"question_id": 10, "is_correct": 1, "awarded_points": 1},
            {"question_id": 11, "is_correct": 0, "awarded_points": 0},
            {"question_id": 12, "is_correct": 0, "awarded_points": 0},
            {"question_id": 14, "is_correct": 0, "awarded_points": 0.25},
        ])
        connection = FakeConnection(cursor)

        with patch("main.get_db", return_value=connection):
            result = main.get_student_submission_review(submission_id=88, student_id=23)

        questions = result["sections"][0]["questions"]
        self.assertEqual(questions[0]["earned_points"], 1)
        self.assertEqual(questions[0]["possible_points"], 1)
        self.assertEqual(questions[1]["earned_points"], 0)
        self.assertEqual(questions[1]["possible_points"], 1)
        self.assertEqual(questions[2]["earned_points"], 0)
        self.assertEqual(questions[2]["possible_points"], 0.5)
        self.assertEqual(result["sections"][1]["questions"][0]["earned_points"], 0)
        self.assertEqual(result["sections"][2]["questions"][0]["earned_points"], 0.25)
        self.assertEqual(result["sections"][2]["questions"][0]["possible_points"], 1)
        self.assertEqual(
            questions[0]["options"],
            [
                {"label": "A", "content": "Phương án A"},
                {"label": "B", "content": "Phương án B"},
            ],
        )
        self.assertNotIn("is_correct", questions[0]["options"][0])
        self.assertNotIn("is_selected", questions[0]["options"][0])
        self.assertEqual(result["sections"][1]["questions"][0]["options"], [])
        self.assertNotIn("selected_option_id", result)
        self.assertTrue(connection.closed)

    def test_student_cannot_review_another_students_submission(self):
        cursor = StudentSubmissionReviewCursor(None, [])
        connection = FakeConnection(cursor)

        with patch("main.get_db", return_value=connection):
            with self.assertRaises(main.HTTPException) as error:
                main.get_student_submission_review(submission_id=88, student_id=23)

        self.assertEqual(error.exception.status_code, 404)
        self.assertTrue(connection.closed)

    def test_submission_detail_includes_correct_and_selected_answers(self):
        submission = {
            "id": 88,
            "exam_id": 7,
            "full_name": "Nguyen Van A",
            "username": "student_a",
            "class_name": "12A1",
            "exam_title": "Bai kiem tra",
            "duration_minutes": 45,
            "score": 0,
            "status": "graded",
            "submitted_at": "2026-11-04 10:00:00",
            "shuffled_data": json.dumps([{
                "id": 2,
                "section_type": "g1",
                "title": "Phan I",
                "questions": [{
                    "id": 10,
                    "number": 1,
                    "content": "Cau hoi",
                    "points": 1,
                    "options": [
                        {"id": 20, "label": "A", "content": "Phuong an sai"},
                        {"id": 21, "label": "B", "content": "Phuong an dung"},
                    ],
                }],
            }]),
        }
        answers = [{
            "question_id": 10,
            "selected_option_id": 20,
            "text_answer": None,
            "awarded_points": 0,
            "is_correct": 0,
        }]
        option_rows = [
            {"id": 20, "is_correct": 0, "content": "Phuong an sai"},
            {"id": 21, "is_correct": 1, "content": "Phuong an dung"},
        ]
        cursor = SubmissionReviewCursor(submission, answers, option_rows)
        connection = FakeConnection(cursor)

        with patch("main.get_db", return_value=connection):
            result = main.get_submission_detail(submission_id=88)

        question = result["submission"]["review_sections"][0]["questions"][0]
        self.assertFalse(question["options"][0]["is_correct"])
        self.assertTrue(question["options"][0]["is_selected"])
        self.assertTrue(question["options"][1]["is_correct"])
        self.assertFalse(question["options"][1]["is_selected"])
        self.assertTrue(connection.closed)


if __name__ == "__main__":
    unittest.main()
