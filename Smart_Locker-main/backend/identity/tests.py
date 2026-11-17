from datetime import datetime, timezone as dt_timezone
from unittest.mock import MagicMock, patch

import requests
from django.test import TestCase, override_settings

from identity import adapters


def fake_response(status_code, data):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = data
    return resp


NOW = datetime.fromtimestamp(1794184790, tz=dt_timezone.utc)


@override_settings(
    SOURCE1_URL="http://source1:9001",
    SOURCE2_URL="http://source2:9002",
    SOURCE2_HMAC_SECRET="demo-secret-123",
)
class AdapterTests(TestCase):
    def test_source2_signature(self):
        with patch("identity.adapters.requests.post") as post:
            post.return_value = fake_response(
                200, {"member_id": "PK-0099", "name": "Tran Ngoc Viet", "active": True}
            )
            info = adapters.lookup_source2("A3F1C290", NOW)
        args, kwargs = post.call_args
        self.assertEqual(args[0], "http://source2:9002/verify")
        self.assertEqual(kwargs["json"], {"uid": "A3F1C290", "ts": 1794184790})
        self.assertEqual(
            kwargs["headers"]["X-Signature"],
            "7f99b7afb93dd7db8d1948271acdc847d7fb81bcee460ec005df107e1ac1fb61",
        )
        self.assertEqual(kwargs["timeout"], 1)
        self.assertEqual(
            info,
            {"source": "PARKING", "external_id": "PK-0099", "name": "Tran Ngoc Viet", "active": True},
        )

    def test_source1_found(self):
        with patch("identity.adapters.requests.get") as get:
            get.return_value = fake_response(
                200, {"student_id": "B23DCCN924", "name": "Trần Ngọc Việt", "status": "active"}
            )
            info = adapters.lookup_source1("A3F1C290")
        self.assertEqual(get.call_args[0][0], "http://source1:9001/students/A3F1C290")
        self.assertEqual(get.call_args[1]["timeout"], 1)
        self.assertEqual(info["source"], "STUDENT")
        self.assertEqual(info["external_id"], "B23DCCN924")
        self.assertTrue(info["active"])

    def test_source1_inactive(self):
        with patch("identity.adapters.requests.get") as get:
            get.return_value = fake_response(
                200, {"student_id": "B23DCCN924", "name": "A", "status": "inactive"}
            )
            info = adapters.lookup_source1("A3F1C290")
        self.assertFalse(info["active"])

    def test_source1_errors_return_none(self):
        with patch("identity.adapters.requests.get") as get:
            get.return_value = fake_response(404, {})
            self.assertIsNone(adapters.lookup_source1("A3F1C290"))
            get.return_value = fake_response(500, {})
            self.assertIsNone(adapters.lookup_source1("A3F1C290"))
            bad = fake_response(200, None)
            bad.json.side_effect = ValueError("hong")
            get.return_value = bad
            self.assertIsNone(adapters.lookup_source1("A3F1C290"))
            get.return_value = fake_response(200, {"student_id": 5, "name": "A", "status": "active"})
            self.assertIsNone(adapters.lookup_source1("A3F1C290"))
            get.side_effect = requests.ConnectionError()
            self.assertIsNone(adapters.lookup_source1("A3F1C290"))

    def test_source1_timeout_falls_back_to_source2(self):
        with patch("identity.adapters.requests.get") as get, patch(
            "identity.adapters.requests.post"
        ) as post:
            get.side_effect = requests.Timeout()
            post.return_value = fake_response(
                200, {"member_id": "PK-0099", "name": "A", "active": True}
            )
            info = adapters.lookup("A3F1C290", NOW)
        self.assertEqual(get.call_count, 1)
        self.assertEqual(post.call_count, 1)
        self.assertEqual(info["source"], "PARKING")

    def test_source1_found_skips_source2(self):
        with patch("identity.adapters.requests.get") as get, patch(
            "identity.adapters.requests.post"
        ) as post:
            get.return_value = fake_response(
                200, {"student_id": "B23DCCN924", "name": "A", "status": "active"}
            )
            info = adapters.lookup("A3F1C290", NOW)
        self.assertEqual(post.call_count, 0)
        self.assertEqual(info["source"], "STUDENT")

    def test_both_not_found(self):
        with patch("identity.adapters.requests.get") as get, patch(
            "identity.adapters.requests.post"
        ) as post:
            get.return_value = fake_response(404, {})
            post.return_value = fake_response(404, {})
            self.assertIsNone(adapters.lookup("A3F1C290", NOW))
