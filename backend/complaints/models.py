from django.db import models


class Complaint(models.Model):
    class Status(models.TextChoices):
        ROUTED = "routed", "Routed"
        DUPLICATE = "duplicate", "Duplicate"
        NEEDS_DETAILS = "needs_details", "Needs details"

    # What the citizen sent
    text = models.TextField()
    location = models.CharField(max_length=255, blank=True)
    photo = models.ImageField(upload_to="photos/", blank=True, null=True)

    # What the agents decided
    ref = models.CharField(max_length=20, blank=True)           # e.g. C-1, from the pipeline
    duplicate_of = models.CharField(max_length=20, blank=True)  # ref of the original
    status = models.CharField(max_length=20, choices=Status.choices,
                              default=Status.ROUTED)
    category = models.CharField(max_length=30, blank=True)
    severity = models.CharField(max_length=10, blank=True)
    reason = models.TextField(blank=True)
    department = models.CharField(max_length=100, blank=True)
    desk = models.CharField(max_length=100, blank=True)
    sla_hours = models.PositiveIntegerField(null=True, blank=True)
    rule = models.TextField(blank=True)
    letter = models.TextField(blank=True)
    note = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.ref or 'pending'} | {self.category} | {self.status}"