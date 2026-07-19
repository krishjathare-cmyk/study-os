import unittest
from datetime import timedelta
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.database import Base
from app.study_organizer import organize_document
from app.study_workflow import (
    create_and_map_assignment_chunks,
    grade_practice_set,
    grade_topic_test,
    public_questions,
    pregenerate_topic_tests_for_nodes,
    regenerate_learning_content,
    regenerate_study_practice_for_nodes,
    set_node_completion,
)


class StudyWorkflowTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine)()

        self.user = models.User(
            full_name="Test User",
            email="workflow@example.com",
            hashed_password="not-used",
        )
        semester = models.Semester(name="Semester 1", user=self.user)
        self.subject = models.Subject(name="Physics", semester=semester)
        self.db.add_all([self.user, semester, self.subject])
        self.db.flush()

        document = models.Document(
            filename="mechanics.pdf",
            file_path="uploads/mechanics.pdf",
            document_type="textbook",
            subject_id=self.subject.id,
            extracted_text="""
CHAPTER 2: Mechanics
2.1 MOTION
2.1.1 Velocity
Velocity is displacement divided by time. Calculate velocity using displacement and time.
2.1.2 Acceleration
Acceleration is the change in velocity divided by time.
""",
        )
        self.db.add(document)
        self.db.flush()
        organize_document(self.db, document, use_llm=False)
        self.db.flush()

        self.topic = self.db.query(models.StudyNode).filter_by(node_type="topic").one()
        self.subtopics = self.db.query(models.StudyNode).filter_by(
            node_type="subtopic"
        ).order_by(models.StudyNode.heading_number).all()

    def tearDown(self):
        self.db.close()

    def add_assignment(self, text: str) -> models.AssignmentDocument:
        assignment = models.AssignmentDocument(
            subject_id=self.subject.id,
            filename="assignment.pdf",
            file_path="uploads/assignment.pdf",
            extracted_text=text,
        )
        self.db.add(assignment)
        self.db.flush()
        return assignment

    @patch("app.study_workflow.map_assignment_chunks", return_value=None)
    def test_assignment_mapping_is_conservative(self, _):
        relevant = self.add_assignment(
            "Velocity displacement and time. Calculate velocity from displacement and time. "
            * 30
        )
        relevant_chunks, affected = create_and_map_assignment_chunks(self.db, relevant)
        self.assertTrue(affected)
        self.assertTrue(any(chunk.mapping_status == "mapped" for chunk in relevant_chunks))

        unrelated = self.add_assignment(
            "Write an essay about medieval poetry and literary characters. " * 30
        )
        unrelated_chunks, unrelated_affected = create_and_map_assignment_chunks(
            self.db,
            unrelated,
        )
        self.assertEqual([], unrelated_affected)
        self.assertTrue(all(chunk.mapping_status == "unmapped" for chunk in unrelated_chunks))

    @patch("app.study_workflow.generate_node_learning_content", return_value=None)
    def test_learning_content_is_stored_and_versioned(self, _):
        first = regenerate_learning_content(self.db, self.subtopics[0])
        self.assertTrue(first.explanation)
        self.assertEqual(1, first.version)

        second = regenerate_learning_content(self.db, self.subtopics[0])
        self.assertEqual(first.id, second.id)
        self.assertEqual(2, second.version)

    @patch("app.study_workflow.generate_question_set", return_value=None)
    def test_completion_schedules_revision_and_creates_one_topic_test(self, _):
        first_progress, first_revisions, first_test = set_node_completion(
            self.db,
            self.user.id,
            self.subtopics[0],
            True,
        )
        self.assertEqual("completed", first_progress.status)
        self.assertEqual([4, 7, 15], [item.interval_days for item in first_revisions])
        self.assertIsNone(first_test)

        _, _, topic_test = set_node_completion(
            self.db,
            self.user.id,
            self.subtopics[1],
            True,
        )
        self.assertIsNotNone(topic_test)
        self.assertEqual(
            topic_test.created_at.date() + timedelta(days=15),
            topic_test.due_at.date(),
        )
        self.assertEqual(10, len(topic_test.questions))
        self.assertNotIn("correct_answer", public_questions(topic_test.questions)[0])

        _, _, repeated_test = set_node_completion(
            self.db,
            self.user.id,
            self.topic,
            True,
        )
        self.assertEqual(topic_test.id, repeated_test.id)
        self.assertEqual(1, self.db.query(models.TopicTest).count())

    @patch("app.study_workflow.generate_question_set", return_value=None)
    def test_test_submission_persists_score_analytics(self, _):
        _, _, test = set_node_completion(
            self.db,
            self.user.id,
            self.topic,
            True,
        )
        answers = {
            str(question["id"]): question["correct_answer"]
            for question in test.questions
        }
        attempt = grade_topic_test(self.db, test, self.user.id, answers)

        self.assertEqual(100.0, attempt.percentage)
        self.assertEqual([], attempt.analytics["weak_concepts"])
        self.assertEqual("submitted", test.status)

    def test_practice_submission_persists_score_and_feedback(self):
        practice = models.PracticeSet(
            node_id=self.subtopics[0].id,
            title="Practice: Velocity",
            questions=[
                {
                    "id": 1,
                    "question": "What is velocity?",
                    "options": ["Displacement per time", "Mass", "Force", "Energy"],
                    "correct_answer": "Displacement per time",
                    "explanation": "Velocity relates displacement to elapsed time.",
                    "concept": "Velocity",
                },
            ],
        )
        self.db.add(practice)
        self.db.flush()

        attempt = grade_practice_set(
            self.db,
            practice,
            self.user.id,
            {"1": "Mass"},
        )

        self.assertEqual(0.0, attempt.percentage)
        self.assertEqual(["Velocity"], attempt.analytics["weak_concepts"])
        self.assertFalse(attempt.analytics["question_feedback"][0]["correct"])
        self.assertEqual("Displacement per time", attempt.analytics["question_feedback"][0]["correct_answer"])

    @patch("app.study_workflow.generate_question_set", return_value=None)
    def test_upload_generation_is_reused_when_topic_is_completed(self, generator):
        node_ids = [node.id for node in self.subtopics]
        regenerate_study_practice_for_nodes(self.db, node_ids)
        pregenerate_topic_tests_for_nodes(self.db, self.user.id, node_ids)
        locked_test = self.db.query(models.TopicTest).one()
        self.assertEqual("locked", locked_test.status)

        generator.reset_mock()
        set_node_completion(self.db, self.user.id, self.subtopics[0], True)
        _, _, activated_test = set_node_completion(
            self.db,
            self.user.id,
            self.subtopics[1],
            True,
        )

        self.assertEqual(locked_test.id, activated_test.id)
        self.assertEqual("pending", activated_test.status)
        generator.assert_not_called()


if __name__ == "__main__":
    unittest.main()
