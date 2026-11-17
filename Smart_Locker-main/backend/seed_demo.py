import hashlib
from datetime import timedelta
import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.contrib.auth.models import Group, User
from django.utils import timezone
from devices.models import Device
from identity.models import CardUser
from lockers.models import Compartment, Event, FeeRule, Session
from payments.models import Payment


def run():
    now = timezone.now()

    # 1. Groups & Dashboard accounts
    admin_group, _ = Group.objects.get_or_create(name="admin")
    viewer_group, _ = Group.objects.get_or_create(name="viewer")

    admin_user, _ = User.objects.get_or_create(username="admin")
    admin_user.set_password("123")
    admin_user.is_staff = True
    admin_user.save()
    admin_user.groups.set([admin_group])

    viewer_user, _ = User.objects.get_or_create(username="viewer")
    viewer_user.set_password("123")
    viewer_user.save()
    viewer_user.groups.set([viewer_group])

    # 2. FeeRule
    FeeRule.objects.update_or_create(
        id=1,
        defaults={
            "free_min": 5,
            "block_min": 60,
            "block_fee": 2000,
            "updated_at": now,
            "updated_by": admin_user,
        },
    )

    # 3. Device LOCKER01 with known token matching config.h
    token = "05af1eacdf664b9f26493caebbb90f6b"
    token_hash = hashlib.sha256(token.encode("ascii")).hexdigest()
    device, _ = Device.objects.update_or_create(
        device_id="LOCKER01",
        defaults={
            "token_hash": token_hash,
            "firmware_version": "1.0.3",
            "last_heartbeat_at": now,
            "last_rssi": -54,
            "last_free_heap": 184320,
            "last_pending_count": 0,
        },
    )

    comp1, _ = Compartment.objects.update_or_create(
        device=device,
        number=1,
        defaults={
            "status": "FREE",
            "has_item": False,
            "door_closed": True,
            "status_changed_at": now - timedelta(minutes=10),
            "last_unlock_at": now - timedelta(minutes=15),
        },
    )

    comp2, _ = Compartment.objects.update_or_create(
        device=device,
        number=2,
        defaults={
            "status": "FREE",
            "has_item": False,
            "door_closed": True,
            "status_changed_at": now - timedelta(minutes=25),
            "last_unlock_at": now - timedelta(minutes=25),
        },
    )

    # 4. Sample CardUsers
    u1, _ = CardUser.objects.update_or_create(
        card_uid="0FA4E001",
        defaults={
            "name": "Nguyen Van An",
            "source": "LOCAL",
            "external_id": None,
            "blocked": False,
            "created_at": now - timedelta(days=3),
        },
    )
    u2, _ = CardUser.objects.update_or_create(
        card_uid="A3F1C290",
        defaults={
            "name": "Tran Thi Binh",
            "source": "STUDENT",
            "external_id": "SV2023001",
            "blocked": False,
            "created_at": now - timedelta(days=2),
        },
    )
    u3, _ = CardUser.objects.update_or_create(
        card_uid="B7E2D104",
        defaults={
            "name": "Le Hoang Nam",
            "source": "PARKING",
            "external_id": "PK00981",
            "blocked": False,
            "created_at": now - timedelta(days=1),
        },
    )
    u4, _ = CardUser.objects.update_or_create(
        card_uid="C9D8E7F6",
        defaults={
            "name": "Pham Minh Tuan",
            "source": "LOCAL",
            "external_id": None,
            "blocked": True,
            "created_at": now - timedelta(days=1),
        },
    )

    # 5. Historical closed sessions + payments + 1 active OCCUPIED session on Compartment 2
    if not Session.objects.exists():
        s1 = Session.objects.create(
            user=u1,
            compartment=comp1,
            state="CLOSED",
            created_at=now - timedelta(hours=5),
            door_opened_at=now - timedelta(hours=5) + timedelta(seconds=3),
            occupied_at=now - timedelta(hours=5) + timedelta(seconds=15),
            closed_at=now - timedelta(hours=4, minutes=30),
            duration_min=30,
            fee=0,
            payment_status="NONE",
        )
        s2 = Session.objects.create(
            user=u2,
            compartment=comp1,
            state="CLOSED",
            created_at=now - timedelta(hours=3),
            door_opened_at=now - timedelta(hours=3) + timedelta(seconds=4),
            occupied_at=now - timedelta(hours=3) + timedelta(seconds=12),
            closed_at=now - timedelta(hours=1, minutes=40),
            duration_min=80,
            fee=4000,
            payment_status="PAID",
        )
        Payment.objects.create(
            session=s2,
            pay_code="P00101",
            source="STUDENT",
            amount=4000,
            state="PAID",
            created_at=now - timedelta(hours=1, minutes=42),
            expires_at=now - timedelta(hours=1, minutes=40),
            paid_at=now - timedelta(hours=1, minutes=41),
        )
        # Historical session on comp2 for u3 (already CLOSED so both compartments are FREE for live hardware test)
        s3 = Session.objects.create(
            user=u3,
            compartment=comp2,
            state="CLOSED",
            created_at=now - timedelta(hours=2),
            door_opened_at=now - timedelta(hours=2) + timedelta(seconds=2),
            occupied_at=now - timedelta(hours=2) + timedelta(seconds=10),
            closed_at=now - timedelta(minutes=25),
            duration_min=95,
            fee=4000,
            payment_status="PAID",
        )
    else:
        Session.objects.filter(state__in=["CREATED", "OPEN", "OCCUPIED", "RELEASING"]).update(
            state="CLOSED",
            closed_at=now,
            duration_min=25,
            fee=0,
        )
        Event.objects.get_or_create(
            device=device,
            request_id="LOCKER01-000001",
            defaults={
                "event_type": "BOOT",
                "session": None,
                "compartment_number": None,
                "has_item": False,
                "device_time": now - timedelta(hours=6),
                "received_at": now - timedelta(hours=6),
                "accepted": True,
                "error_code": "",
            },
        )

    print("SEED_OK")
    print("ADMIN_USER: admin / PASS: 123")
    print("VIEWER_USER: viewer / PASS: 123")
    print("DEVICE_ID: LOCKER01")
    print("DEVICE_TOKEN:", token)


if __name__ == "__main__":
    run()
