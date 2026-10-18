from __future__ import annotations

import unittest

from comfy_discord.resolutions import parse_image_resolution


class ResolutionTests(unittest.TestCase):
    def test_parses_common_resolution_formats(self) -> None:
        self.assertEqual(parse_image_resolution("1024x1024"), (1024, 1024))
        self.assertEqual(parse_image_resolution(" 888 × 1184 "), (888, 1184))
        self.assertEqual(parse_image_resolution("1368X768"), (1368, 768))

    def test_rejects_invalid_resolution_format(self) -> None:
        with self.assertRaisesRegex(ValueError, "BREITExHOEHE"):
            parse_image_resolution("1024:1024")

    def test_rejects_dimensions_outside_supported_range(self) -> None:
        with self.assertRaisesRegex(ValueError, "zwischen 256 und 2048"):
            parse_image_resolution("128x4096")


if __name__ == "__main__":
    unittest.main()
