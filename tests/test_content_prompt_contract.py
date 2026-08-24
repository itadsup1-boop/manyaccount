import unittest

from apps.creator_article.article_ai_script import load_prompt as load_article_prompt
from apps.creator_facebook.fb_ai_script import load_prompt as load_video_prompt


REQUIRED_FIELDS = (
    '"schema_version"',
    '"story_type"',
    '"main_angle"',
    '"audience_payoff"',
    '"hook_variants"',
    '"selected_hook"',
    '"selected_hook_reason"',
    '"evidence"',
    '"beats"',
    '"retention_risks"',
    '"risk_flags"',
)


class ContentPromptContractTests(unittest.TestCase):
    def assert_prompt_contract(self, prompt):
        for field_name in REQUIRED_FIELDS:
            self.assertIn(field_name, prompt)
        self.assertEqual(prompt.count('"hook_type"'), 3)
        self.assertIn('"hook_type": "result"', prompt)
        self.assertIn('"hook_type": "conflict"', prompt)
        self.assertIn('"hook_type": "impact"', prompt)
        self.assertIn('"role": "hook"', prompt)

    def test_article_prompt_uses_content_schema(self):
        self.assert_prompt_contract(load_article_prompt())

    def test_video_prompt_uses_content_schema(self):
        self.assert_prompt_contract(load_video_prompt())


if __name__ == "__main__":
    unittest.main()
