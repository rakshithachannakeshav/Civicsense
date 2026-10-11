from rest_framework import mixins, viewsets
from rest_framework.exceptions import APIException

from agents import process_complaint
from .models import Complaint
from .serializers import ComplaintSerializer


class TriageUnavailable(APIException):
    status_code = 503
    default_detail = "The triage service is unavailable right now. Try again shortly."


class ComplaintViewSet(mixins.CreateModelMixin,
                       mixins.ListModelMixin,
                       mixins.RetrieveModelMixin,
                       viewsets.GenericViewSet):
    queryset = Complaint.objects.all()
    serializer_class = ComplaintSerializer

    def perform_create(self, serializer):
        complaint = serializer.save()
        complaint.ref = f"C-{complaint.pk}"      # unique, from the database id
        image_path = complaint.photo.path if complaint.photo else None

        # Earlier originals to compare against (the new row has no vectors yet)
        known = [
            {"ref": c.ref, "category": c.category,
             "desc_vec": c.desc_vec, "loc_vec": c.loc_vec}
            for c in Complaint.objects.filter(
                status=Complaint.Status.ROUTED, desc_vec__isnull=False
            )
        ]

        try:
            result = process_complaint(
                complaint.text, complaint.location, image_path,
                known=known, complaint_id=complaint.ref,
            )
        except Exception:
            complaint.delete()          # do not keep a half-processed complaint
            raise TriageUnavailable()   # for example, when the daily quota is used up

        complaint.category = result.get("category", "")
        complaint.severity = result.get("severity", "")
        complaint.reason = result.get("reason", "")

        if result.get("duplicate_of"):
            complaint.status = Complaint.Status.DUPLICATE
            complaint.duplicate_of = result["duplicate_of"]
            complaint.note = result.get("note", "")
        elif result.get("letter"):
            complaint.status = Complaint.Status.ROUTED
            complaint.department = result["department"]
            complaint.desk = result["desk"]
            complaint.sla_hours = result["sla_hours"]
            complaint.rule = result["rule"]
            complaint.letter = result["letter"]
            complaint.desc_vec = result["desc_vec"]
            complaint.loc_vec = result["loc_vec"]
        else:
            complaint.status = Complaint.Status.NEEDS_DETAILS
            complaint.department = result.get("department", "Pending")
            complaint.note = result.get("note", "")

        complaint.save()