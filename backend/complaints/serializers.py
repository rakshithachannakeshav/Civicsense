from rest_framework import serializers

from .models import Complaint


class ComplaintSerializer(serializers.ModelSerializer):
    class Meta:
        model = Complaint
        exclude = ["desc_vec", "loc_vec"]
        # The citizen supplies only text, location and photo.
        # Everything else is filled in by the agents.
        read_only_fields = [
            "ref", "duplicate_of", "status", "category", "severity", "reason",
            "department", "desk", "sla_hours", "rule", "letter", "note",
            "created_at",
        ]