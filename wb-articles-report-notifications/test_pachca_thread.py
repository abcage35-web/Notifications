#!/usr/bin/env python3
import unittest
from unittest.mock import Mock, patch

from send_pachca_report import create_thread, send_message


class PachcaThreadTest(unittest.TestCase):
    @patch("send_pachca_report.requests.post")
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

    @patch("send_pachca_report.requests.post")
    def test_thread_is_created_and_used_as_message_entity(self, post):
        thread_response = Mock()
        thread_response.json.return_value = {"data": {"id": 456}}
        message_response = Mock()
        message_response.json.return_value = {"data": {"id": 789}}
        post.side_effect = [thread_response, message_response]

        thread_id = create_thread("token", 123)
        thread_message_id = send_message("token", "discussion", thread_id, "niches")

        self.assertEqual(thread_id, 456)
        self.assertEqual(thread_message_id, 789)
        self.assertTrue(post.call_args_list[0].args[0].endswith("/messages/123/thread"))
        thread_payload = post.call_args_list[1].kwargs["json"]["message"]
        self.assertEqual(thread_payload["entity_id"], 456)
        self.assertNotIn("files", thread_payload)


if __name__ == "__main__":
    unittest.main()
