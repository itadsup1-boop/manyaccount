import json

from apps.creator_article.article_chatgpt_automator import (
    _extract_last_json_object,
    _looks_like_generated_result,
)


def test_prompt_schema_is_not_treated_as_generated_result():
    prompt = '''Hãy trả JSON:
    {"title_tiktok": "", "hook": "", "script_voice": "", "should_make_video": true}
    '''
    candidate = _extract_last_json_object(prompt)

    assert candidate
    assert not _looks_like_generated_result(candidate)


def test_generated_result_with_content_is_accepted():
    result = {
        "title_tiktok": "Cảnh báo trước khi làm đẹp",
        "hook": "Chi tiết này có thể thay đổi quyết định của bạn.",
        "script_voice": "Hãy kiểm tra thông tin trước khi quyết định.",
        "should_make_video": True,
    }

    assert _looks_like_generated_result(json.dumps(result, ensure_ascii=False))
