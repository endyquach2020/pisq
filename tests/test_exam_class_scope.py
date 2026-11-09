import asyncio
import os
import tempfile
import unittest
from unittest.mock import patch

import main


class FakeCursor:
    def __init__(self):
        self.queries = []
        self.lastrowid = 1

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, query, params=None):
        self.queries.append((query, params))

    def fetchone(self):
        return {"id": 1}


class FakeConnection:
    def __init__(self, cursor):
        self.fake_cursor = cursor
        self.closed = False

    def cursor(self):
        return self.fake_cursor

    def commit(self):
        pass

    def close(self):
        self.closed = True


class FakeUploadFile:
    filename = "exam.docx"

    async def read(self):
        return b"test docx"


class ExamClassScopeTests(unittest.TestCase):
    def test_import_without_class_assigns_exam_to_all_classes(self):
        cursor = FakeCursor()
        connection = FakeConnection(cursor)
        sections = [{
            "section_type": "g1",
            "title": "Phần I",
            "questions": [{"content": "Câu 1", "options": []}],
        }]

        with tempfile.TemporaryDirectory() as upload_dir:
            with (
                patch("main.UPLOAD_DIR", upload_dir),
                patch("main.get_db", return_value=connection),
                patch("main.parse_docx_file", return_value=sections),
            ):
                result = asyncio.run(main.import_exam_docx(
                    title="Kiểm tra",
                    class_id=None,
                    duration_minutes=45,
                    total_score=10.0,
                    is_published=1,
                    file=FakeUploadFile(),
                ))
            self.assertEqual(os.listdir(upload_dir), [])

        exam_insert = next(
            (params for query, params in cursor.queries if "INSERT INTO exams" in query),
            None,
        )
        self.assertIsNotNone(exam_insert)
        self.assertIsNone(exam_insert[2])
        self.assertEqual(result["status"], "success")
        self.assertTrue(connection.closed)


if __name__ == "__main__":
    unittest.main()
