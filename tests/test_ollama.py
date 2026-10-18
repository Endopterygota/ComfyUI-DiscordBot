from __future__ import annotations

import unittest

from comfy_discord.ollama import OllamaClient, OllamaError, split_discord_text


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

    def test_long_reply_is_split_for_discord(self) -> None:
        text = ("Ein sinnvoller Satz mit mehreren Woertern. " * 150).strip()
        chunks = split_discord_text(text, limit=200)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(1 <= len(chunk) <= 200 for chunk in chunks))


if __name__ == "__main__":
    unittest.main()
