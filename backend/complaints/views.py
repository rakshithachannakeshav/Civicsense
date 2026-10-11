from django.shortcuts import render
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
        image_path = complaint.photo.path if complaint.photo else None

        try:
            result = process_complaint(complaint.text, complaint.location, image_path)
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
            complaint.ref = result["complaint_id"]
            complaint.department = result["department"]
            complaint.desk = result["desk"]
            complaint.sla_hours = result["sla_hours"]
            complaint.rule = result["rule"]
            complaint.letter = result["letter"]
        else:
            complaint.status = Complaint.Status.NEEDS_DETAILS
            complaint.department = result.get("department", "Pending")
            complaint.note = result.get("note", "")

        complaint.save()

# Create your views here.
