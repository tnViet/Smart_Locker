from django.db import models


class Payment(models.Model):
    session = models.ForeignKey("lockers.Session", on_delete=models.PROTECT)
    pay_code = models.CharField(max_length=6, unique=True)
    source = models.CharField(max_length=8)
    amount = models.IntegerField()
    state = models.CharField(max_length=8)
    created_at = models.DateTimeField()
    expires_at = models.DateTimeField()
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "payments"
