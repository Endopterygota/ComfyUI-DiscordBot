from __future__ import annotations

import unittest

from comfy_discord.ollama import OllamaClient, OllamaError, prepare_embed_text


class OllamaTests(unittest.TestCase):
    def test_parse_reply_extracts_content_and_metrics(self) -> None:
        reply = OllamaClient._parse_reply(
            {
                "message": {"role": "assistant", "content": "  Hallo Discord!  "},
                "prompt_eval_count": 12,
                "eval_count": 34,
                "total_duration": 2_500_000_000,
            }
        )
        self.assertEqual(reply.content, "Hallo Discord!")
        self.assertEqual(reply.prompt_tokens, 12)
        self.assertEqual(reply.response_tokens, 34)
        self.assertEqual(reply.total_duration_seconds, 2.5)

    def test_parse_reply_rejects_empty_content(self) -> None:
        with self.assertRaisesRegex(OllamaError, "leere Antwort"):
            OllamaClient._parse_reply({"message": {"content": "  "}})

    def test_reply_fits_in_one_embed(self) -> None:
        text, needs_file = prepare_embed_text("Eine kurze Antwort.", limit=200)
        self.assertEqual(text, "Eine kurze Antwort.")
        self.assertFalse(needs_file)

    def test_oversized_reply_uses_preview_and_attachment(self) -> None:
        text, needs_file = prepare_embed_text("Wort " * 100, limit=200)
        self.assertLessEqual(len(text), 200)
        self.assertTrue(text.endswith("Vollstaendige Antwort siehe angehaengte Datei."))
        self.assertTrue(needs_file)


if __name__ == "__main__":
    unittest.main()
