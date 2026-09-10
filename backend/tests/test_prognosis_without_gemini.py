import unittest

from services.prognosis_service import run_prognosis


class PrognosisWithoutGeminiTest(unittest.TestCase):
    def test_run_prognosis_without_gemini_uses_heuristic_fallback(self):
        result = run_prognosis(
            b"",
            b"",
            humidity=82,
            temperature=29,
            ndvi=0.28,
            plant_id="demo",
        )

        self.assertIn(result["risk_level"], {"low", "moderate", "high"})
        self.assertIn("summary", result)
        self.assertIn("precautions", result)
        self.assertTrue(len(result["precautions"]) >= 2)
        self.assertTrue(len(result["watch_signs"]) >= 2)


if __name__ == "__main__":
    unittest.main()
