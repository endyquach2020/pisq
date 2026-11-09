import os
import unittest
from unittest.mock import patch

import database


class InitCursor:
    def __init__(self):
        self.queries = []
        self.current_query = ""
        self.inserted_users = []
        self.inserted_classes = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, query, params=None):
        self.current_query = query
        self.queries.append((query, params))
        if "INSERT INTO users" in query:
            self.inserted_users.append(params)
        if "INSERT INTO classes" in query:
            self.inserted_classes.append(params)

    def fetchone(self):
        if "FROM users WHERE role = 'admin'" in self.current_query:
            return None
        if "FROM classes LIMIT 1" in self.current_query:
            return None
        if "FROM users WHERE username = 'nguyenvanan'" in self.current_query:
            return None
        return {"column_count": 1}

    def fetchall(self):
        if "information_schema.columns" in self.current_query:
            return [
                {"column_name": column}
                for column in (
                    "id",
                    "exam_id",
                    "student_id",
                    "start_time",
                    "submitted_at",
                    "score",
                    "status",
                    "shuffled_data",
                    "created_at",
                    "class_id",
                    "drive_upload_status",
                    "drive_upload_detail",
                    "drive_file_id",
                    "drive_file_url",
                    "drive_upload_attempts",
                )
            ]
        return []

    @property
    def lastrowid(self):
        return 1


class InitConnection:
    def __init__(self):
        self.fake_cursor = InitCursor()
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


class DatabaseInitTests(unittest.TestCase):
    def test_production_uses_configured_admin_password_without_demo_accounts(self):
        connection = InitConnection()
        with patch("database.get_db", return_value=connection), patch.dict(
            os.environ,
            {
                "ENVIRONMENT": "production",
                "ADMIN_DEFAULT_PASSWORD": "unique-test-password",
            },
            clear=False,
        ):
            database.init_default_data()

        self.assertEqual(len(connection.fake_cursor.inserted_users), 1)
        self.assertEqual(
            connection.fake_cursor.inserted_users[0][1],
            database.hash_password("unique-test-password"),
        )
        self.assertEqual(connection.fake_cursor.inserted_classes, [])
        self.assertTrue(connection.committed)
        self.assertTrue(connection.closed)

    def test_production_does_not_create_admin_without_configured_password(self):
        connection = InitConnection()
        with patch("database.get_db", return_value=connection), patch.dict(
            os.environ,
            {"ENVIRONMENT": "production"},
            clear=False,
        ):
            os.environ.pop("ADMIN_DEFAULT_PASSWORD", None)
            database.init_default_data()

        self.assertEqual(connection.fake_cursor.inserted_users, [])
        self.assertEqual(connection.fake_cursor.inserted_classes, [])
        self.assertTrue(connection.rolled_back)
        self.assertTrue(connection.closed)


if __name__ == "__main__":
    unittest.main()
