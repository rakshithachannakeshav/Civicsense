from rest_framework import serializers

from .models import Complaint


class ComplaintSerializer(serializers.ModelSerializer):
    submitted_by = serializers.SerializerMethodField()

    class Meta:
        model = Complaint
        exclude = ["desc_vec", "loc_vec", "owner"]
        # The citizen supplies only text, location and photo.
        # Everything else is filled in by the agents.
        read_only_fields = [
            "ref", "duplicate_of", "status", "category", "severity", "reason",
            "department", "desk", "sla_hours", "rule", "letter", "note",
            "created_at", "fu_status", "fu_level", "fu_window", "fu_due_hour",
            "fu_reminded", "fu_history",
        ]

    def get_submitted_by(self, obj):
        return obj.owner.username if obj.owner else ""
