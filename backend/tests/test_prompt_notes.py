import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app import schemas
from app.llm_provider import edit_structured_notes


class _FakeCompletions:
    def __init__(self, payload):
        self.payload = payload
        self.request = None

    def create(self, **kwargs):
        self.request = kwargs
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=json.dumps(self.payload))
                )
            ]
        )


class PromptNotesTests(unittest.TestCase):
    def test_note_document_schema_accepts_structured_sections(self):
        notes = schemas.PromptNoteData.model_validate(
            {
                "overview": "Velocity describes displacement over time.",
                "sections": [
                    {
                        "heading": "Definition",
                        "summary": "A rate of change of position.",
                        "points": ["Use signed displacement.", "Keep units consistent."],
                    }
                ],
                "key_points": ["Velocity has direction."],
                "questions": ["How does velocity differ from speed?"],
            }
        )
        self.assertEqual("Definition", notes.sections[0].heading)
        self.assertEqual(2, len(notes.sections[0].points))

    def test_editor_uses_the_shared_chat_model_and_strict_shape(self):
        payload = {
            "message": "Condensed the notes.",
            "notes": {
                "overview": "Velocity is displacement per unit time.",
                "sections": [
                    {
                        "heading": "Core idea",
                        "summary": "Velocity is a directed rate.",
                        "points": ["v = displacement / time"],
                    }
                ],
                "key_points": ["Velocity includes direction."],
                "questions": ["What makes velocity negative?"],
            },
        }
        completions = _FakeCompletions(payload)
        client = SimpleNamespace(
            chat=SimpleNamespace(completions=completions)
        )

        with (
            patch("app.llm_provider._get_openai_client", return_value=client),
            patch("app.llm_provider._remote_llm_enabled", return_value=True),
            patch(
                "app.llm_provider._model_for",
                return_value="shared-chat-model",
            ) as model_for,
        ):
            result = edit_structured_notes(
                "Mechanics / Motion / Velocity",
                "Velocity is displacement divided by time.",
                payload["notes"],
                "Make this concise",
            )

        model_for.assert_called_once_with("CHAT_MODEL", "gpt-4.1-mini")
        self.assertEqual("shared-chat-model", completions.request["model"])
        self.assertEqual(0, completions.request["temperature"])
        self.assertEqual(
            "json_schema",
            completions.request["response_format"]["type"],
        )
        self.assertEqual(payload, result)


if __name__ == "__main__":
    unittest.main()
