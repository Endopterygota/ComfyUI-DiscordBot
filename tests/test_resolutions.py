from __future__ import annotations

import unittest

from comfy_discord.resolutions import dimensions_for_megapixels


class ResolutionTests(unittest.TestCase):
    def test_one_megapixel_square_is_1024_square(self) -> None:
        self.assertEqual(dimensions_for_megapixels(1024, 1024, 1.0), (1024, 1024))

    def test_megapixels_scale_area_without_changing_aspect_ratio(self) -> None:
        width, height = dimensions_for_megapixels(888, 1184, 1.5)
        self.assertAlmostEqual(width / height, 3 / 4, places=3)
        self.assertAlmostEqual(width * height, 1.5 * 1024 * 1024, delta=2000)

    def test_rejects_non_positive_megapixel_value(self) -> None:
        with self.assertRaisesRegex(ValueError, "groesser als 0"):
            dimensions_for_megapixels(1024, 1024, 0)


if __name__ == "__main__":
    unittest.main()
