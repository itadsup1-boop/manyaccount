import ast
import os
import unittest


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PIPELINE_FILES = (
    "apps/creator_article/article_pipeline_core.py",
    "apps/creator_facebook/fb_pipeline.py",
    "shared/core/worker.py",
    "apps/uploader_tiktok/desktop_ui/pages/auto_clone_worker_page.py",
)


def _call_name(node):
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return ""


class UploadQAGateTests(unittest.TestCase):
    def test_every_drive_upload_has_an_earlier_qa_call_in_same_function(self):
        checked_uploads = 0
        for relative_path in PIPELINE_FILES:
            path = os.path.join(PROJECT_ROOT, relative_path)
            with open(path, "r", encoding="utf-8") as file:
                tree = ast.parse(file.read(), filename=path)
            for function in (
                node for node in ast.walk(tree)
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            ):
                calls = [node for node in ast.walk(function) if isinstance(node, ast.Call)]
                upload_lines = [
                    node.lineno for node in calls
                    if _call_name(node) == "upload_video_to_drive"
                ]
                if not upload_lines:
                    continue
                qa_lines = [
                    node.lineno for node in calls
                    if _call_name(node) == "run_video_qa"
                ]
                self.assertTrue(qa_lines, f"Thiếu VideoQA trong {relative_path}:{function.name}")
                for upload_line in upload_lines:
                    self.assertTrue(
                        any(qa_line < upload_line for qa_line in qa_lines),
                        f"Upload trước QA trong {relative_path}:{upload_line}",
                    )
                    checked_uploads += 1
        self.assertEqual(4, checked_uploads)
