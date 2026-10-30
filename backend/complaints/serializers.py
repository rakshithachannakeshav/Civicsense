from rest_framework import serializers

from .gps import photo_gps
from .models import Complaint


class ComplaintSerializer(serializers.ModelSerializer):
    submitted_by = serializers.SerializerMethodField()

    # The browser's position, used only when the photo has no GPS of its own
    device_lat = serializers.FloatField(write_only=True, required=False,
                                        min_value=-90, max_value=90)
    device_lng = serializers.FloatField(write_only=True, required=False,
                                        min_value=-180, max_value=180)

    class Meta:
        model = Complaint
        exclude = ["desc_vec", "loc_vec", "owner"]
        # The citizen supplies text, location, a photo and (optionally) the
        # device position. Everything else is filled in by the server.
        read_only_fields = [
            "ref", "duplicate_of", "status", "category", "severity", "reason",
            "department", "desk", "sla_hours", "rule", "letter", "note",
            "created_at", "fu_status", "fu_level", "fu_window", "fu_due_hour",
            "fu_reminded", "fu_history", "latitude", "longitude", "gps_source",
        ]
        extra_kwargs = {"photo": {"required": True, "allow_null": False}}

    def get_submitted_by(self, obj):
        return obj.owner.username if obj.owner else ""

    def validate(self, attrs):
        device_lat = attrs.pop("device_lat", None)
        device_lng = attrs.pop("device_lng", None)
        if (device_lat is None) != (device_lng is None):
            raise serializers.ValidationError(
                {"device_lat": "Send both device_lat and device_lng, or neither."})

        gps = photo_gps(attrs["photo"])
        if gps:
            attrs["latitude"], attrs["longitude"] = gps
            attrs["gps_source"] = "photo"
        elif device_lat is not None:
            attrs["latitude"] = round(device_lat, 6)
            attrs["longitude"] = round(device_lng, 6)
            attrs["gps_source"] = "device"
        else:
            raise serializers.ValidationError({"photo": (
                "We need the GPS location of the problem. This photo has no location "
                "data, so allow location access in your browser and submit again."
            )})
        return attrs
