import os
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.database import Base
from app.main import get_study_node_detail, get_subject_study_tree
from app.pdf_utils import StyledPDFLine
from app.study_organizer import (
    NodeSpec,
    OrganizedSection,
    _limit_document_subtopics,
    extract_outline_sections,
    organize_document,
)


class StudyOrganizerTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine)()

        user = models.User(
            full_name="Test User",
            email="test@example.com",
            hashed_password="not-used",
        )
        semester = models.Semester(name="Semester 1", user=user)
        self.subject = models.Subject(name="Physics", semester=semester)
        self.db.add_all([user, semester, self.subject])
        self.db.flush()
        self.user = user

    def tearDown(self):
        self.db.close()

    def add_document(self, filename: str, text: str) -> models.Document:
        document = models.Document(
            filename=filename,
            file_path=f"uploads/{filename}",
            document_type="textbook",
            extracted_text=text,
            subject_id=self.subject.id,
        )
        self.db.add(document)
        self.db.flush()
        return document

    @staticmethod
    def oversized_document_sections(count: int = 10) -> list[OrganizedSection]:
        document_topic = NodeSpec("Deep Learning PDF", level=2)
        section_topic = NodeSpec("Neural Networks", level=2)
        return [
            OrganizedSection(
                path=[
                    document_topic,
                    section_topic,
                    NodeSpec(f"Detected Section {index}", level=3),
                ],
                text=f"SOURCE_MARKER_{index} material for section {index}.",
            )
            for index in range(count)
        ]

    def test_eight_or_fewer_document_subtopics_do_not_call_ai(self):
        sections = self.oversized_document_sections(8)
        with patch("app.study_organizer.consolidate_subtopics") as consolidate:
            result = _limit_document_subtopics(sections)

        self.assertIs(result, sections)
        consolidate.assert_not_called()

    def test_more_than_eight_document_subtopics_use_one_ai_plan(self):
        sections = self.oversized_document_sections(10)
        plan = [
            {"title": "Core Foundations", "section_indexes": [0, 1, 2]},
            *[
                {"title": f"Consolidated Topic {index}", "section_indexes": [index]}
                for index in range(3, 10)
            ],
        ]
        with patch(
            "app.study_organizer.consolidate_subtopics",
            return_value=plan,
        ) as consolidate:
            result = _limit_document_subtopics(sections)

        self.assertEqual(8, len(result))
        consolidate.assert_called_once()
        self.assertEqual(8, len({section.path[-1].title for section in result}))
        merged_text = "\n".join(section.text for section in result)
        for index in range(10):
            self.assertIn(f"SOURCE_MARKER_{index}", merged_text)

    def test_invalid_ai_plan_still_falls_back_to_eight_subtopics(self):
        sections = self.oversized_document_sections(11)
        with patch(
            "app.study_organizer.consolidate_subtopics",
            return_value=[{"title": "Incomplete", "section_indexes": [0]}],
        ):
            result = _limit_document_subtopics(sections)

        self.assertEqual(8, len(result))
        merged_text = "\n".join(section.text for section in result)
        for index in range(11):
            self.assertIn(f"SOURCE_MARKER_{index}", merged_text)

    def test_document_outline_applies_the_eight_subtopic_limit(self):
        text = "CHAPTER 1: Fundamentals\n" + "\n".join(
            f"1.{index + 1} Detected Topic {index}\nMaterial marker {index}."
            for index in range(11)
        )
        with (
            patch.dict(os.environ, {"SUBTOPIC_CONSOLIDATION_ENABLED": "true"}),
            patch("app.study_organizer.consolidate_subtopics", return_value=None),
        ):
            sections = extract_outline_sections(
                text,
                "fundamentals.pdf",
                use_llm=False,
                document_as_topic=True,
            )

        self.assertEqual(8, len(sections))
        self.assertEqual(8, len({_section.path[-1].title for _section in sections}))
        merged_text = "\n".join(section.text for section in sections)
        for index in range(11):
            self.assertIn(f"Material marker {index}", merged_text)

    def test_detects_hierarchy_and_ignores_equations(self):
        text = """
Light and Optics
10CHAPTER
10.2 SPHERICAL MIRRORS
Mirrors reflect light.
10.2.1 Image Formation
Images can be real or virtual.
1.50 + 2.00 = 3.50
P = P1 + P2
"""
        sections = extract_outline_sections(text, "optics.pdf", use_llm=False)
        paths = [[node.title for node in section.path] for section in sections]

        self.assertIn(
            ["Light and Optics", "SPHERICAL MIRRORS", "Image Formation"],
            paths,
        )
        titles = {title for path in paths for title in path}
        self.assertNotIn("1.50 + 2.00 = 3.50", titles)
        self.assertNotIn("P = P1 + P2", titles)

    def test_font_metadata_builds_hierarchy_without_llm(self):
        styled_lines = [
            StyledPDFLine("Deep Learning", 1, 24, "Arial-Bold", True, 0, 50),
            StyledPDFLine("Neural Networks", 1, 18, "Arial-Bold", True, 1, 90),
            StyledPDFLine(
                "Layers and Representation",
                1,
                14,
                "Arial-Bold",
                True,
                2,
                130,
            ),
            StyledPDFLine(
                "Information is processed through several layers.",
                1,
                11,
                "Arial",
                False,
                3,
                170,
            ),
        ]

        sections = extract_outline_sections(
            "",
            "deep-learning.pdf",
            use_llm=False,
            styled_lines=styled_lines,
        )

        self.assertEqual(
            ["Deep Learning", "Neural Networks", "Layers And Representation"],
            [node.title for node in sections[0].path],
        )

    def test_extension_pdf_merges_by_numbered_path(self):
        first = self.add_document(
            "chapter-10.pdf",
            """
Light and Optics
10CHAPTER
10.2 SPHERICAL MIRRORS
10.2.1 Image Formation
First document content about images.
""",
        )
        extension = self.add_document(
            "chapter-10-extension.pdf",
            """
10.2.2 Sign Convention
Second document extends the same topic.
""",
        )

        first_result = organize_document(self.db, first, use_llm=False)
        extension_result = organize_document(self.db, extension, use_llm=False)
        self.db.flush()

        chapters = self.db.query(models.StudyNode).filter_by(node_type="chapter").all()
        topics = self.db.query(models.StudyNode).filter_by(node_type="topic").all()
        subtopics = self.db.query(models.StudyNode).filter_by(node_type="subtopic").all()

        self.assertEqual(1, len(chapters))
        self.assertEqual("10", chapters[0].heading_number)
        self.assertEqual(1, len(topics))
        self.assertEqual("10.2", topics[0].heading_number)
        self.assertEqual({"10.2.1", "10.2.2"}, {node.heading_number for node in subtopics})
        self.assertGreater(first_result.chunks_linked, 0)
        self.assertGreater(extension_result.chunks_linked, 0)

    def test_document_can_be_the_top_level_topic(self):
        document = self.add_document(
            "cnn_fundamentals.pdf",
            """
CHAPTER 1: Fundamentals
1.1 Neural Networks
Neural networks use layers of parameters.
1.2 Convolution
Convolution extracts local patterns.
1.2.1 Filters
Filters learn useful visual features.
""",
        )
        organize_document(self.db, document, use_llm=False, document_as_topic=True)
        self.db.flush()

        roots = self.db.query(models.StudyNode).filter_by(parent_id=None).all()
        self.assertEqual(1, len(roots))
        self.assertEqual("topic", roots[0].node_type)
        self.assertEqual("cnn fundamentals", roots[0].normalized_title)

        children = sorted(roots[0].children, key=lambda node: node.sort_order)
        self.assertEqual({"Neural Networks", "Convolution"}, {node.title for node in children})
        neural = next(node for node in children if node.title == "Neural Networks")
        convolution = next(node for node in children if node.title == "Convolution")
        self.assertEqual("subtopic", neural.node_type)
        self.assertEqual("topic", convolution.node_type)
        self.assertEqual(["Overview", "Filters"], [node.title for node in convolution.children])

    def test_numbered_sections_switch_chapters_and_word_chapters_update_titles(self):
        document = self.add_document(
            "physics.pdf",
            """
3.1 INTRODUCTION
Current electricity content.
Chapter Three
CURRENT
ELECTRICITY
4.1 INTRODUCTION
Moving charges content.
Chapter Four
MOVING CHARGES
AND MAGNETISM
4.2 MAGNETIC FIELD
Magnetic field content.
""",
        )
        organize_document(self.db, document, use_llm=False)
        chapters = self.db.query(models.StudyNode).filter_by(node_type="chapter").order_by(
            models.StudyNode.heading_number
        ).all()

        self.assertEqual(["3", "4"], [chapter.heading_number for chapter in chapters])
        self.assertEqual(["CURRENT ELECTRICITY", "MOVING CHARGES AND MAGNETISM"], [
            chapter.title for chapter in chapters
        ])

    def test_lower_numbered_reference_does_not_create_false_chapter(self):
        document = self.add_document(
            "magnetism.pdf",
            """
4.1 INTRODUCTION
Chapter Four
MOVING CHARGES
AND MAGNETISM
1.7 MV Tandetrons in Atomic Minerals Directorate for Exploration and Research, Hyderabad
4.2 MAGNETIC FORCE
Magnetic force content.
""",
        )
        organize_document(self.db, document, use_llm=False)
        chapters = self.db.query(models.StudyNode).filter_by(node_type="chapter").all()

        self.assertEqual(["4"], [chapter.heading_number for chapter in chapters])

    def test_every_chunk_has_one_subtopic_link(self):
        document = self.add_document(
            "unstructured-notes.pdf",
            "These notes have useful material but no visible headings. " * 80,
        )
        result = organize_document(self.db, document, use_llm=False)
        self.db.flush()

        chunks = self.db.query(models.DocumentChunk).filter_by(document_id=document.id).all()
        links = (
            self.db.query(models.StudyNodeChunk)
            .join(models.DocumentChunk)
            .filter(models.DocumentChunk.document_id == document.id)
            .all()
        )

        self.assertEqual(len(chunks), len(links))
        self.assertEqual(len(chunks), len(result.subtopic_ids))
        self.assertTrue(all(link.node.node_type == "subtopic" for link in links))

    def test_tree_and_leaf_detail_are_frontend_ready(self):
        document = self.add_document(
            "mechanics.pdf",
            """
CHAPTER 2: Mechanics
2.1 MOTION
2.1.1 Velocity
Velocity is displacement divided by time.
""",
        )
        organize_document(self.db, document, use_llm=False)
        self.db.flush()

        tree = get_subject_study_tree(self.subject.id, self.db, self.user)
        leaf = tree[0]["children"][0]["children"][0]
        detail = get_study_node_detail(
            self.subject.id,
            leaf["id"],
            self.db,
            self.user,
        )

        self.assertEqual("subtopic", leaf["node_type"])
        self.assertEqual(["Mechanics", "MOTION", "Velocity"], [
            item["title"] for item in detail["breadcrumb"]
        ])
        self.assertEqual(document.id, detail["chunks"][0]["document_id"])

    def test_repeat_organization_returns_existing_vector_payload(self):
        document = self.add_document(
            "repeatable.pdf",
            "1.1 TOPIC\n1.1.1 Subtopic\nMaterial that should be indexed.",
        )
        first = organize_document(self.db, document, use_llm=False)
        self.db.flush()
        repeated = organize_document(self.db, document, use_llm=False)

        self.assertTrue(repeated.skipped)
        self.assertEqual(first.chunk_texts, repeated.chunk_texts)
        self.assertEqual(first.subtopic_ids, repeated.subtopic_ids)


if __name__ == "__main__":
    unittest.main()
