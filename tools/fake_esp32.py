"""Gia lap firmware ESP32 de chay thu toan luong backend Smart Locker (buoc B9).

Chay lan luot: BOOT, /sync, gui do, lay do mien phi, lay do co phi, mat mang roi
gui bu, lenh mo thu cong. Moi buoc kiem tra phan hoi, sai thi dung va bao loi.

Can co san:
- Thiet bi tao bang: python manage.py create_device LOCKER01 (lay token in ra)
- Tai khoan dashboard thuoc group admin (de them the LOCAL, sua bang gia, mo thu cong)
- Buoc lay do co phi can may chu mo phong nguon 1 hoac 2 dang chay va the --student-card
  co trong du lieu mau. Thieu thi buoc nay duoc bo qua.

Vi du:
  python tools/fake_esp32.py --token <token> --admin-user admin --admin-pass <mk>
      --student-card A3F1C290 --pay-secret demo-pay-456

Luu y: khoa can nghi 60 giay giua hai lan mo cung mot ngan (Quy chuan API 1.7),
nen script co cac doan cho, tong thoi gian chay khoang 4 den 5 phut.
"""
import argparse
import hashlib
import hmac
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone

import requests

VN = timezone(timedelta(hours=7))
REST_WAIT_SEC = 62
SEQ_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".fake_esp32_seq")


class StepFailed(Exception):
    pass


class FakeEsp32:
    def __init__(self, args):
        self.base = args.url.rstrip("/")
        self.device_id = args.device
        self.token = args.token
        self.args = args
        self.jwt = None
        self.seq = self.load_seq()

    # ------------------------------------------------------------------
    # Bo dem request_id, giong khoa req_seq trong NVS: tang dan, khong reset

    def load_seq(self):
        try:
            with open(SEQ_FILE, "r", encoding="ascii") as f:
                return int(f.read().strip())
        except (OSError, ValueError):
            return 0

    def next_request_id(self):
        self.seq = self.seq + 1
        if self.seq > 999999:
            raise StepFailed("Bo dem request_id vuot 999999, xoa file " + SEQ_FILE)
        with open(SEQ_FILE, "w", encoding="ascii") as f:
            f.write(str(self.seq))
        return "%s-%06d" % (self.device_id, self.seq)

    def device_time(self):
        return datetime.now(VN).replace(microsecond=0).isoformat()

    # ------------------------------------------------------------------
    # Goi HTTP

    def device_call(self, method, path, body):
        headers = {"Authorization": "Device " + self.token}
        url = self.base + path
        if method == "GET":
            resp = requests.get(url, headers=headers, timeout=10)
        else:
            raw = json.dumps(body, separators=(",", ":"))
            headers["Content-Type"] = "application/json"
            resp = requests.post(url, data=raw, headers=headers, timeout=10)
        if len(resp.content) > 2048:
            raise StepFailed("Phan hoi %s dai %d byte, vuot bo dem 2048" % (path, len(resp.content)))
        return resp.json()

    def admin_call(self, method, path, body):
        headers = {"Authorization": "Bearer " + self.jwt}
        resp = requests.request(method, self.base + path, json=body, headers=headers, timeout=10)
        return resp.json()

    def scan(self, card_uid):
        body = {
            "device_id": self.device_id,
            "card_uid": card_uid,
            "request_id": self.next_request_id(),
            "device_time": self.device_time(),
        }
        return self.device_call("POST", "/scan", body)

    def make_event(self, event_type, session_id, compartment, has_item):
        return {
            "device_id": self.device_id,
            "request_id": self.next_request_id(),
            "device_time": self.device_time(),
            "event_type": event_type,
            "session_id": session_id,
            "compartment": compartment,
            "has_item": has_item,
            "firmware_version": "",
        }

    def event(self, event_type, session_id, compartment, has_item):
        body = self.make_event(event_type, session_id, compartment, has_item)
        return self.device_call("POST", "/events", body)

    def sync(self):
        return self.device_call("GET", "/sync?device_id=" + self.device_id, None)

    def heartbeat(self):
        body = {
            "device_id": self.device_id,
            "uptime_sec": 120,
            "rssi": -58,
            "free_heap": 142000,
            "pending_count": 0,
        }
        return self.device_call("POST", "/heartbeat", body)

    def ack(self, command_id, result):
        body = {
            "device_id": self.device_id,
            "request_id": self.next_request_id(),
            "device_time": self.device_time(),
            "result": result,
        }
        return self.device_call("POST", "/commands/%d/ack" % command_id, body)

    def payment_check(self, session_id):
        body = {
            "device_id": self.device_id,
            "request_id": self.next_request_id(),
            "device_time": self.device_time(),
            "session_id": session_id,
        }
        return self.device_call("POST", "/payment/check", body)

    # ------------------------------------------------------------------
    # Kiem tra

    def expect_ok(self, resp, what):
        if not resp.get("success"):
            raise StepFailed("%s: that bai %s %s" % (what, resp.get("error_code"), resp.get("message")))
        return resp["data"]

    def expect_equal(self, actual, expected, what):
        if actual != expected:
            raise StepFailed("%s: mong %r, nhan %r" % (what, expected, actual))

    def wait_rest(self, reason):
        print("   ... cho %d giay nghi khoa (%s)" % (REST_WAIT_SEC, reason), flush=True)
        time.sleep(REST_WAIT_SEC)

    def compartment_status(self, number):
        data = self.expect_ok(self.sync(), "/sync")
        for comp in data["compartments"]:
            if comp["number"] == number:
                return comp
        raise StepFailed("/sync khong co ngan %d" % number)

    def deposit(self, card_uid):
        data = self.expect_ok(self.scan(card_uid), "Quet the gui do")
        self.expect_equal(data["action"], "DEPOSIT", "action")
        number = data["compartment"]
        session_id = data["session_id"]
        print("   DEPOSIT: phien %d, ngan %d, OLED '%s'" % (session_id, number, data["display"]))
        data = self.expect_ok(self.event("DOOR_OPENED", session_id, number, False), "DOOR_OPENED")
        self.expect_equal(data["session_state"], "OPEN", "phien sau DOOR_OPENED")
        data = self.expect_ok(self.event("DOOR_CLOSED", session_id, number, True), "DOOR_CLOSED")
        self.expect_equal(data["session_state"], "OCCUPIED", "phien sau DOOR_CLOSED")
        self.expect_equal(data["display"], "Da khoa - Hen gap lai", "display")
        print("   Da khoa, phien OCCUPIED")
        return session_id, number

    def take_out(self, session_id, number):
        data = self.expect_ok(self.event("DOOR_OPENED", session_id, number, True), "DOOR_OPENED")
        data = self.expect_ok(self.event("DOOR_CLOSED", session_id, number, False), "DOOR_CLOSED")
        self.expect_equal(data["session_state"], "CLOSED", "phien sau khi lay do")
        self.expect_equal(data["compartment_status"], "FREE", "ngan sau khi lay do")
        print("   Lay do xong, phien CLOSED, ngan %d FREE" % number)

    def pickup_free(self, card_uid, session_id, number):
        data = self.expect_ok(self.scan(card_uid), "Quet the lay do")
        self.expect_equal(data["action"], "PICKUP", "action")
        self.expect_equal(data["fee"], 0, "fee")
        self.expect_equal(data["session_id"], session_id, "session_id")
        print("   PICKUP: %d phut, phi %d, OLED '%s'" % (data["duration_min"], data["fee"], data["display"]))
        self.take_out(session_id, number)

    # ------------------------------------------------------------------
    # Cac buoc

    def setup(self):
        print("== Chuan bi: dang nhap dashboard, them the LOCAL")
        resp = requests.post(
            self.base + "/auth/login",
            json={"username": self.args.admin_user, "password": self.args.admin_pass},
            timeout=10,
        ).json()
        data = self.expect_ok(resp, "Dang nhap dashboard")
        if data["role"] != "admin":
            raise StepFailed("Tai khoan dashboard phai thuoc group admin")
        self.jwt = data["access_token"]
        resp = self.admin_call("POST", "/users", {"card_uid": self.args.local_card, "name": "The thu fake_esp32"})
        if resp.get("success"):
            print("   Da them the LOCAL " + self.args.local_card)
        elif resp.get("error_code") == "INVALID_PAYLOAD":
            print("   The LOCAL %s da co san" % self.args.local_card)
        else:
            raise StepFailed("Them the LOCAL: %s" % resp)

    def step_boot(self):
        print("== 1. BOOT")
        body = self.make_event("BOOT", 0, 0, False)
        body["firmware_version"] = self.args.firmware
        data = self.expect_ok(self.device_call("POST", "/events", body), "BOOT")
        self.expect_equal(data["session_state"], "", "session_state cua BOOT")

    def step_sync(self):
        print("== 2. /sync")
        data = self.expect_ok(self.sync(), "/sync")
        print("   server_time " + data["server_time"])
        for comp in data["compartments"]:
            print("   Ngan %d: %s, cua dong %s, phien %d" % (
                comp["number"], comp["status"], comp["door_closed"], comp["session_id"]))
            if comp["status"] != "FREE" or comp["session_id"] != 0:
                raise StepFailed(
                    "Ngan %d khong FREE. Dua tu ve trang thai trong (lay do, hoac reset tren dashboard) roi chay lai"
                    % comp["number"])

    def step_deposit_and_free_pickup(self):
        print("== 3. Gui do (the LOCAL %s)" % self.args.local_card)
        session_id, number = self.deposit(self.args.local_card)
        print("== 4. Lay do mien phi")
        data = self.scan(self.args.local_card)
        self.expect_equal(data.get("error_code"), "TOO_SOON", "quet lai ngay sau khi gui")
        print("   Quet ngay: TOO_SOON dung nhu mong doi")
        self.wait_rest("ngan %d" % number)
        self.pickup_free(self.args.local_card, session_id, number)
        return number

    def step_paid_pickup(self):
        print("== 5. Lay do co phi (the %s)" % self.args.student_card)
        if not self.args.student_card or not self.args.pay_secret:
            print("   BO QUA: can --student-card va --pay-secret")
            return "skipped"

        rule = self.expect_ok(self.admin_call("GET", "/fee-rules", None), "Doc bang gia")
        try:
            # Ha bang gia de chi can gui hon 1 phut la co phi
            self.expect_ok(
                self.admin_call("PATCH", "/fee-rules", {"free_min": 0, "block_min": 1, "block_fee": 2000}),
                "Sua bang gia tam thoi",
            )
            resp = self.scan(self.args.student_card)
            if resp.get("error_code") == "CARD_NOT_FOUND":
                print("   BO QUA: the khong co o nguon 1 va nguon 2 (may chu mo phong chua chay?)")
                return "skipped"
            data = self.expect_ok(resp, "Quet the gui do")
            self.expect_equal(data["action"], "DEPOSIT", "action")
            session_id = data["session_id"]
            number = data["compartment"]
            self.expect_ok(self.event("DOOR_OPENED", session_id, number, False), "DOOR_OPENED")
            self.expect_ok(self.event("DOOR_CLOSED", session_id, number, True), "DOOR_CLOSED")
            print("   Da gui do o ngan %d, phien %d" % (number, session_id))
            self.wait_rest("ngan %d, dong thoi de qua 1 phut tinh phi" % number)

            resp = self.scan(self.args.student_card)
            if resp.get("error_code") == "PAYMENT_UNAVAILABLE":
                print("   PAYMENT_UNAVAILABLE: he thong thu phi khong tra loi. Lay do bang danh dau thu tay")
                self.expect_ok(self.admin_call("POST", "/sessions/%d/pay" % session_id, None), "Danh dau PAID")
                self.pickup_free_after_paid(session_id, number)
                return "skipped"
            data = self.expect_ok(resp, "Quet the lay do")
            self.expect_equal(data["action"], "PAYMENT", "action")
            if len(data["qr"]) > 47:
                raise StepFailed("qr dai %d ky tu" % len(data["qr"]))
            print("   PAYMENT: %d phut, phi %d, qr %s, han %d giay" % (
                data["duration_min"], data["fee"], data["qr"], data["pay_timeout_sec"]))
            pay_code = data["qr"].rsplit("/", 1)[1]
            fee = data["fee"]

            data = self.expect_ok(self.payment_check(session_id), "/payment/check lan 1")
            self.expect_equal(data["paid"], False, "paid truoc khi tra tien")

            # Dong vai trang thanh toan cua he thong ngoai: khach bam xac nhan
            ts = int(time.time())
            text = "%s|%d|%d" % (pay_code, fee, ts)
            signature = hmac.new(self.args.pay_secret.encode(), text.encode(), hashlib.sha256).hexdigest()
            resp = requests.post(
                self.base + "/payments/callback",
                json={"pay_code": pay_code, "amount": fee, "ts": ts, "signature": signature},
                timeout=10,
            ).json()
            data = self.expect_ok(resp, "Callback thanh toan")
            print("   Callback: phien %d, duplicate %s" % (data["session_id"], data["duplicate"]))

            data = self.expect_ok(self.payment_check(session_id), "/payment/check lan 2")
            self.expect_equal(data["paid"], True, "paid sau khi tra tien")
            print("   Da thanh toan, mo khoa %d ms, OLED '%s'" % (data["unlock_ms"], data["display"]))
            self.take_out(session_id, number)
            return "ok"
        finally:
            self.admin_call("PATCH", "/fee-rules", {
                "free_min": rule["free_min"], "block_min": rule["block_min"], "block_fee": rule["block_fee"],
            })
            print("   Da tra bang gia ve %d/%d/%d" % (rule["free_min"], rule["block_min"], rule["block_fee"]))

    def pickup_free_after_paid(self, session_id, number):
        data = self.expect_ok(self.scan(self.args.student_card), "Quet the sau khi danh dau PAID")
        self.expect_equal(data["action"], "PICKUP", "action")
        self.take_out(session_id, number)

    def step_offline_batch(self):
        print("== 6. Mat mang roi gui bu")
        data = self.expect_ok(self.scan(self.args.local_card), "Quet the gui do")
        session_id = data["session_id"]
        number = data["compartment"]
        print("   DEPOSIT o ngan %d, phien %d. Mat Wi-Fi, luu su kien vao NVS" % (number, session_id))
        opened = self.make_event("DOOR_OPENED", session_id, number, False)
        closed = self.make_event("DOOR_CLOSED", session_id, number, True)

        # Gui nguoc thu tu de kiem tra backend xep theo so dem trong request_id
        batch = {"device_id": self.device_id, "events": [closed, opened]}
        data = self.expect_ok(self.device_call("POST", "/events/batch", batch), "/events/batch")
        for result in data["results"]:
            self.expect_equal(result["accepted"], True, "accepted cua " + result["request_id"])
        comp = self.compartment_status(number)
        self.expect_equal(comp["status"], "OCCUPIED", "ngan sau gui bu")
        print("   Gui bu xong, ngan %d OCCUPIED" % number)

        data = self.expect_ok(self.device_call("POST", "/events/batch", batch), "/events/batch lan 2")
        for result in data["results"]:
            self.expect_equal(result["accepted"], True, "accepted lan 2")
        self.expect_equal(self.compartment_status(number)["status"], "OCCUPIED", "ngan sau gui bu lan 2")
        print("   Gui bu lan 2: moi phan tu accepted, trang thai khong doi")

        self.wait_rest("ngan %d" % number)
        self.pickup_free(self.args.local_card, session_id, number)
        return number

    def step_manual_open(self, number):
        print("== 7. Mo ngan %d thu cong tu dashboard" % number)
        data = self.expect_ok(
            self.admin_call("POST", "/admin/open", {
                "device_id": self.device_id, "compartment": number, "reason": "Chay thu fake_esp32",
            }),
            "/admin/open",
        )
        command_id = data["command_id"]
        data = self.expect_ok(self.heartbeat(), "/heartbeat")
        commands = data["pending_commands"]
        if len(commands) != 1 or commands[0]["command_id"] != command_id:
            raise StepFailed("Heartbeat khong tra lenh %d: %s" % (command_id, commands))
        print("   Heartbeat nhan lenh %d, mo ngan %d trong %d ms" % (
            command_id, commands[0]["compartment"], commands[0]["unlock_ms"]))
        self.expect_ok(self.ack(command_id, "DONE"), "ack DONE")
        self.expect_equal(self.compartment_status(number)["status"], "OPEN", "ngan sau ack")
        self.expect_ok(self.event("DOOR_OPENED", 0, number, False), "DOOR_OPENED")
        data = self.expect_ok(self.event("DOOR_CLOSED", 0, number, False), "DOOR_CLOSED")
        self.expect_equal(data["compartment_status"], "FREE", "ngan sau khi dong")
        data = self.expect_ok(self.heartbeat(), "/heartbeat")
        self.expect_equal(data["pending_commands"], [], "lenh sau ack")
        print("   Ack DONE, cua mo roi dong, ngan %d FREE" % number)

    def run(self):
        self.setup()
        self.step_boot()
        self.step_sync()
        used = self.step_deposit_and_free_pickup()
        paid = self.step_paid_pickup()
        used = self.step_offline_batch()
        # Ngan vua lay do xong chua nghi du 60 giay
        self.wait_rest("ngan %d truoc khi mo thu cong" % used)
        self.step_manual_open(used)
        return paid


def main():
    parser = argparse.ArgumentParser(description="Gia lap ESP32 chay thu backend Smart Locker")
    parser.add_argument("--url", default="http://localhost:8000/api/v1")
    parser.add_argument("--device", default="LOCKER01")
    parser.add_argument("--token", required=True, help="Token in ra boi create_device")
    parser.add_argument("--admin-user", required=True)
    parser.add_argument("--admin-pass", required=True)
    parser.add_argument("--local-card", default="0FA4E001", help="The LOCAL se duoc them qua dashboard")
    parser.add_argument("--student-card", default="", help="The co trong du lieu mau cua nguon 1 hoac 2")
    parser.add_argument("--pay-secret", default="", help="PAY_HMAC_SECRET de ky callback")
    parser.add_argument("--firmware", default="1.0.3")
    args = parser.parse_args()

    started = time.time()
    try:
        paid = FakeEsp32(args).run()
    except StepFailed as exc:
        print("\nTHAT BAI: " + str(exc))
        sys.exit(1)
    except requests.RequestException as exc:
        print("\nLOI KET NOI: " + str(exc))
        sys.exit(2)
    print("\nXONG sau %d giay. Lay do co phi: %s" % (time.time() - started, paid))


if __name__ == "__main__":
    main()
