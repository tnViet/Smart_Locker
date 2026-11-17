import hashlib
import re
import secrets

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from devices.models import Device
from lockers.models import Compartment


class Command(BaseCommand):
    help = "Tao thiet bi moi kem 2 ngan, in token dung mot lan"

    def add_arguments(self, parser):
        parser.add_argument("device_id")

    def handle(self, device_id, **options):
        # Dinh dang gui tin chuong 2: device_id toi da 16 ky tu, chu hoa va so
        if re.fullmatch(r"[A-Z0-9]{1,16}", device_id) is None:
            raise CommandError("device_id chi gom chu hoa va so, toi da 16 ky tu")
        if Device.objects.filter(device_id=device_id).exists():
            raise CommandError("device_id da ton tai")

        token = secrets.token_hex(16)
        token_hash = hashlib.sha256(token.encode("ascii")).hexdigest()
        now = timezone.now()

        with transaction.atomic():
            device = Device.objects.create(device_id=device_id, token_hash=token_hash)
            for number in [1, 2]:
                Compartment.objects.create(
                    device=device,
                    number=number,
                    status="FREE",
                    has_item=False,
                    door_closed=True,
                    status_changed_at=now,
                    last_unlock_at=None,
                )

        self.stdout.write(token)
