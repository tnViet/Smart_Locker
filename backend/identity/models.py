from django.db import models


class CardUser(models.Model):
    card_uid = models.CharField(max_length=8, unique=True)
    name = models.CharField(max_length=100)
    source = models.CharField(max_length=8)
    external_id = models.CharField(max_length=16, null=True, blank=True)
    blocked = models.BooleanField(default=False)
    created_at = models.DateTimeField()

    class Meta:
        db_table = "users"
