import unittest

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models, schemas
from app.database import Base
from app.main import login_user, register_user, require_student_account


class AccountModeTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine)()

    def tearDown(self):
        self.db.close()

    def test_professional_registration_creates_pdf_library(self):
        professional = register_user(
            schemas.UserCreate(
                full_name="Professional User",
                email="professional@example.com",
                password="secure-password",
                account_type="professional",
            ),
            self.db,
        )

        self.assertEqual("professional", professional.account_type)
        library = self.db.query(models.Semester).filter_by(
            user_id=professional.id,
        ).one()
        self.assertEqual("Professional library", library.name)

        login = login_user(
            schemas.LoginRequest(
                email="professional@example.com",
                password="secure-password",
            ),
            self.db,
        )
        self.assertEqual("professional", login["user"].account_type)

    def test_professional_cannot_use_student_only_features(self):
        professional = models.User(
            full_name="Professional User",
            email="pro@example.com",
            hashed_password="not-used",
            account_type="professional",
        )
        with self.assertRaises(HTTPException) as raised:
            require_student_account(professional)
        self.assertEqual(403, raised.exception.status_code)

        student = models.User(
            full_name="Student User",
            email="student@example.com",
            hashed_password="not-used",
            account_type="student",
        )
        self.assertIsNone(require_student_account(student))


if __name__ == "__main__":
    unittest.main()
