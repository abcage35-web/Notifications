#!/usr/bin/env python3
import unittest
import importlib.util
import io
import tempfile
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import Mock, patch


MODULE_PATH = Path(__file__).resolve().with_name("send_pachca_report.py")
SPEC = importlib.util.spec_from_file_location("wb_articles_send_pachca_report", MODULE_PATH)
SEND_MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SEND_MODULE)
create_thread = SEND_MODULE.create_thread
send_message = SEND_MODULE.send_message
split_markdown_messages = SEND_MODULE.split_markdown_messages


class PachcaThreadTest(unittest.TestCase):
    @patch.object(SEND_MODULE, "create_thread")
    @patch.object(SEND_MODULE, "send_message")
    @patch.object(SEND_MODULE, "upload_file")
    @patch.object(SEND_MODULE, "build_report")
    @patch.object(SEND_MODULE, "required_env")
    def test_main_sends_two_root_messages_and_details_in_summary_thread(
        self,
        required_env,
        build_report,
        upload_file,
        send_message,
        create_thread,
    ):
        required_env.side_effect = ["token", "42"]
        send_message.side_effect = [111, 222, 333]
        create_thread.return_value = {"id": 456, "chat_id": 654}
        upload_file.side_effect = [
            {"key": "report", "name": "report.md", "file_type": "file", "size": 1},
            {"key": "niches", "name": "details.md", "file_type": "file", "size": 1},
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            md_path = temp / "report.md"
            root_path = temp / "root.md"
            niche_path = temp / "niches.md"
            detail_path = temp / "details.md"
            md_path.write_text("file", encoding="utf-8")
            root_path.write_text("root", encoding="utf-8")
            niche_path.write_text("summary", encoding="utf-8")
            detail_path.write_text("details", encoding="utf-8")
            build_report.return_value = {
                "md": str(md_path),
                "message": str(root_path),
                "niche_message": str(niche_path),
                "niche_thread_message": str(detail_path),
            }

            with redirect_stdout(io.StringIO()):
                SEND_MODULE.main()

        self.assertEqual(send_message.call_args_list[0].args[:4], ("token", "discussion", "42", "root"))
        self.assertEqual(send_message.call_args_list[1].args[:4], ("token", "discussion", "42", "summary"))
        self.assertEqual(send_message.call_args_list[1].args[4][0]["key"], "niches")
        create_thread.assert_called_once_with("token", 222)
        self.assertEqual(send_message.call_args_list[2].args, ("token", "thread", 456, "details"))

    def test_long_niche_report_is_split_below_pachca_limit(self):
        content = "\n\n".join(["**Ниша**\n" + "x" * 9_000 for _ in range(6)])

        chunks = split_markdown_messages(content, limit=20_000)

        self.assertGreater(len(chunks), 1)
        self.assertEqual("\n\n".join(chunks), content)
        self.assertTrue(all(len(chunk) <= 20_000 for chunk in chunks))

    @patch.object(SEND_MODULE.requests, "post")
    def test_root_message_keeps_attachment(self, post):
        response = Mock()
        response.json.return_value = {"data": {"id": 123}}
        post.return_value = response
        attachment = {"key": "reports/report.md", "name": "report.md", "file_type": "file", "size": 42}

        message_id = send_message("token", "discussion", 39531378, "root", [attachment])

        self.assertEqual(message_id, 123)
        payload = post.call_args.kwargs["json"]["message"]
        self.assertEqual(payload["entity_id"], 39531378)
        self.assertEqual(payload["files"], [attachment])

    @patch.object(SEND_MODULE.requests, "post")
    def test_thread_is_created_and_used_as_message_entity(self, post):
        thread_response = Mock()
        thread_response.json.return_value = {"data": {"id": 456, "chat_id": 654}}
        message_response = Mock()
        message_response.json.return_value = {"data": {"id": 789}}
        post.side_effect = [thread_response, message_response]

        thread = create_thread("token", 123)
        thread_message_id = send_message("token", "thread", thread["id"], "niches")

        self.assertEqual(thread, {"id": 456, "chat_id": 654})
        self.assertEqual(thread_message_id, 789)
        self.assertTrue(post.call_args_list[0].args[0].endswith("/messages/123/thread"))
        thread_payload = post.call_args_list[1].kwargs["json"]["message"]
        self.assertEqual(thread_payload["entity_id"], 456)
        self.assertEqual(thread_payload["entity_type"], "thread")
        self.assertNotIn("files", thread_payload)


if __name__ == "__main__":
    unittest.main()
