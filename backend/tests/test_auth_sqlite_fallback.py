import unittest

import app as backend_app


class AuthSQLiteFallbackTest(unittest.TestCase):
    def setUp(self):
        backend_app.MYSQL_READY = False
        backend_app.MYSQL_INIT_ERROR = "MySQL not configured"
        with backend_app.get_db() as conn:
            conn.execute("DELETE FROM sessions")
            conn.execute("DELETE FROM users")

    def test_signup_and_login_work_without_mysql(self):
        client = backend_app.app.test_client()

        signup_response = client.post(
            "/auth/signup",
            json={"name": "Test User", "email": "test@example.com", "password": "secret123"},
        )

        self.assertEqual(signup_response.status_code, 201, signup_response.get_data(as_text=True))
        signup_body = signup_response.get_json()
        self.assertIn("token", signup_body)
        self.assertEqual(signup_body["user"]["email"], "test@example.com")

        login_response = client.post(
            "/auth/login",
            json={"email": "test@example.com", "password": "secret123"},
        )

        self.assertEqual(login_response.status_code, 200, login_response.get_data(as_text=True))
        login_body = login_response.get_json()
        self.assertIn("token", login_body)
        self.assertEqual(login_body["user"]["email"], "test@example.com")


if __name__ == "__main__":
    unittest.main()
