from django.conf import settings
from django.db import models
from django.db.models import Q

RUNNING_STATES = ["CREATED", "OPEN", "OCCUPIED", "RELEASING"]


class Compartment(models.Model):
    device = models.ForeignKey("devices.Device", on_delete=models.PROTECT)
    number = models.SmallIntegerField()
    status = models.CharField(max_length=8)
    has_item = models.BooleanField(default=False)
    door_closed = models.BooleanField(default=True)
    status_changed_at = models.DateTimeField()
    last_unlock_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "compartments"
        constraints = [
            models.UniqueConstraint(
                fields=["device", "number"], name="compartments_device_number_uniq"
            ),
        ]


class Session(models.Model):
    id = models.AutoField(primary_key=True)
    user = models.ForeignKey("identity.CardUser", on_delete=models.PROTECT)
    compartment = models.ForeignKey(Compartment, on_delete=models.PROTECT)
    state = models.CharField(max_length=9)
    created_at = models.DateTimeField()
    closed_at = models.DateTimeField(null=True, blank=True)
    door_opened_at = models.DateTimeField(null=True, blank=True)
    occupied_at = models.DateTimeField(null=True, blank=True)
    duration_min = models.IntegerField(null=True, blank=True)
    fee = models.IntegerField(null=True, blank=True)
    payment_status = models.CharField(max_length=8, default="NONE")

    class Meta:
        db_table = "sessions"
        constraints = [
            models.UniqueConstraint(
                fields=["user"],
                condition=Q(state__in=RUNNING_STATES),
                name="sessions_one_running_per_user",
            ),
            models.UniqueConstraint(
                fields=["compartment"],
                condition=Q(state__in=RUNNING_STATES),
                name="sessions_one_running_per_compartment",
            ),
        ]
        indexes = [
            models.Index(fields=["state"], name="sessions_state_idx"),
            models.Index(fields=["created_at"], name="sessions_created_at_idx"),
        ]


class Event(models.Model):
    device = models.ForeignKey("devices.Device", on_delete=models.PROTECT)
    request_id = models.CharField(max_length=23)
    event_type = models.CharField(max_length=16)
    session = models.ForeignKey(
        Session, null=True, blank=True, on_delete=models.SET_NULL
    )
    compartment_number = models.SmallIntegerField(null=True, blank=True)
    has_item = models.BooleanField(default=False)
    device_time = models.DateTimeField(null=True, blank=True)
    received_at = models.DateTimeField()
    accepted = models.BooleanField()
    error_code = models.CharField(max_length=20, default="", blank=True)

    class Meta:
        db_table = "events"
        constraints = [
            models.UniqueConstraint(
                fields=["device", "request_id"], name="events_device_request_uniq"
            ),
        ]


class FeeRule(models.Model):
    id = models.SmallIntegerField(primary_key=True)
    free_min = models.IntegerField(default=5)
    block_min = models.IntegerField(default=60)
    block_fee = models.IntegerField(default=2000)
    updated_at = models.DateTimeField()
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )

    class Meta:
        db_table = "fee_rules"
