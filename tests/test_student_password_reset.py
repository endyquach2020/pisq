import unittest
from unittest.mock import patch

from fastapi import HTTPException

import main
from database import hash_password


class FakeCursor:
    def __init__(self, rows=None, result_rows=None):
        self.rows = list(rows or [])
        self.result_rows = result_rows or []
        self.queries = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, query, params=None):
        self.queries.append((query, params))

    def fetchone(self):
        return self.rows.pop(0)

    def fetchall(self):
        return self.result_rows


class FakeConnection:
    def __init__(self, cursor):
        self.fake_cursor = cursor
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def cursor(self):
        return self.fake_cursor

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


class StudentPasswordResetTests(unittest.TestCase):
    def test_student_list_is_filtered_to_selected_class(self):
        student = {"id": 12, "username": "student12", "class_id": 8}
        cursor = FakeCursor(result_rows=[student])
        connection = FakeConnection(cursor)

        with patch("main.get_db", return_value=connection):
            result = main.get_students(class_id=8)

        self.assertEqual(result["students"], [student])
        self.assertIn("u.class_id = %s", cursor.queries[0][0])
        self.assertEqual(cursor.queries[0][1], (8,))
        self.assertTrue(connection.closed)

    def test_reset_requires_admin_credentials_and_stores_only_password_hash(self):
        cursor = FakeCursor([{"id": 1}, {"id": 12}])
        connection = FakeConnection(cursor)
        request = main.ResetStudentPasswordRequest(
            admin_username="admin",
            admin_password="admin-secret",
        )

        with patch("main.get_db", return_value=connection), patch(
            "main.secrets.choice", return_value="A"
        ):
            result = main.reset_student_password(12, request)

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["temporary_password"], "A" * 10)
        auth_query, auth_params = cursor.queries[0]
        self.assertIn("role IN ('admin', 'teacher')", auth_query)
        self.assertEqual(auth_params, ("admin", hash_password("admin-secret")))
        update_query, update_params = cursor.queries[2]
        self.assertIn("role = 'student'", update_query)
        self.assertEqual(update_params, (hash_password("A" * 10), 12))
        self.assertTrue(connection.committed)
        self.assertTrue(connection.closed)

    def test_reset_rejects_invalid_admin_credentials(self):
        cursor = FakeCursor([None])
        connection = FakeConnection(cursor)
        request = main.ResetStudentPasswordRequest(
            admin_username="not-admin",
            admin_password="wrong",
        )

        with patch("main.get_db", return_value=connection), self.assertRaises(
            HTTPException
        ) as raised:
            main.reset_student_password(12, request)

        self.assertEqual(raised.exception.status_code, 403)
        self.assertEqual(len(cursor.queries), 1)
        self.assertTrue(connection.rolled_back)
        self.assertTrue(connection.closed)

    def test_reset_rejects_unknown_student(self):
        cursor = FakeCursor([{"id": 1}, None])
        connection = FakeConnection(cursor)
        request = main.ResetStudentPasswordRequest(
            admin_username="admin",
            admin_password="admin-secret",
        )

        with patch("main.get_db", return_value=connection), self.assertRaises(
            HTTPException
        ) as raised:
            main.reset_student_password(12, request)

        self.assertEqual(raised.exception.status_code, 404)
        self.assertEqual(len(cursor.queries), 2)
        self.assertTrue(connection.rolled_back)
        self.assertTrue(connection.closed)


if __name__ == "__main__":
    unittest.main()
