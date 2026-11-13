from django.conf import settings
from django.db import models


class Device(models.Model):
    device_id = models.CharField(max_length=16, unique=True)
    token_hash = models.CharField(max_length=64)
    firmware_version = models.CharField(max_length=12, default="", blank=True)
    last_heartbeat_at = models.DateTimeField(null=True, blank=True)
    last_rssi = models.SmallIntegerField(null=True, blank=True)
    last_free_heap = models.IntegerField(null=True, blank=True)
    last_pending_count = models.IntegerField(null=True, blank=True)

    class Meta:
        db_table = "devices"


class RequestLog(models.Model):
    device = models.ForeignKey(Device, on_delete=models.CASCADE)
    request_id = models.CharField(max_length=23)
    endpoint = models.CharField(max_length=40)
    response = models.JSONField()
    created_at = models.DateTimeField()

    class Meta:
        db_table = "request_log"
        constraints = [
            models.UniqueConstraint(
                fields=["device", "request_id"], name="request_log_device_request_uniq"
            ),
        ]


class Command(models.Model):
    id = models.AutoField(primary_key=True)
    device = models.ForeignKey(Device, on_delete=models.PROTECT)
    compartment = models.ForeignKey("lockers.Compartment", on_delete=models.PROTECT)
    type = models.CharField(max_length=8)
    unlock_ms = models.SmallIntegerField()
    reason = models.TextField(default="", blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    state = models.CharField(max_length=8)
    created_at = models.DateTimeField()
    acked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "commands"
        indexes = [
            models.Index(fields=["device", "state"], name="commands_device_state_idx"),
        ]
