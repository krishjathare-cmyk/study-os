import unittest
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.database import Base
from app.pdf_jobs import claim_next_job, process_job


class PdfJobTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine)()
        user = models.User(
            full_name="Worker Reader",
            email="worker@example.com",
            hashed_password="hash",
            account_type="student",
            email_verified=True,
        )
        self.db.add(user)
        self.db.flush()
        semester = models.Semester(name="Semester", user_id=user.id)
        self.db.add(semester)
        self.db.flush()
        subject = models.Subject(name="Physics", semester_id=semester.id)
        self.db.add(subject)
        self.db.flush()
        document = models.Document(
            filename="physics.pdf",
            file_path="unused.pdf",
            document_type="textbook",
            processing_status="queued",
            subject_id=subject.id,
        )
        self.db.add(document)
        self.db.flush()
        self.job = models.UploadJob(
            id="job-1",
            user_id=user.id,
            subject_id=subject.id,
            document_id=document.id,
            job_type="study",
        )
        self.db.add(self.job)
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def test_job_is_claimed_and_completed_with_durable_result(self):
        claimed = claim_next_job(self.db)
        self.assertEqual("job-1", claimed)
        self.db.refresh(self.job)
        self.assertEqual("processing", self.job.status)
        self.assertEqual(1, self.job.attempts)

        with patch(
            "app.pdf_jobs._process_study_job",
            return_value={"document_id": self.job.document_id},
        ):
            process_job(self.db, self.job.id)

        self.db.refresh(self.job)
        self.assertEqual("completed", self.job.status)
        self.assertEqual(100, self.job.progress)
        self.assertEqual(self.job.document_id, self.job.result["document_id"])


if __name__ == "__main__":
    unittest.main()
