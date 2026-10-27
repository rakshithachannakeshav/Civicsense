import logging

from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import APIException
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from agents import new_record, process_complaint
from .followup import check
from .models import Complaint
from .permissions import IsOfficial, is_official
from .serializers import ComplaintSerializer

logger = logging.getLogger(__name__)


class TriageUnavailable(APIException):
    status_code = 503
    default_detail = "The triage service is unavailable right now. Try again shortly."


class ComplaintViewSet(mixins.CreateModelMixin,
                       mixins.ListModelMixin,
                       mixins.RetrieveModelMixin,
                       viewsets.GenericViewSet):
    queryset = Complaint.objects.all()
    serializer_class = ComplaintSerializer

    def get_permissions(self):
        if self.action == "resolve":
            return [IsOfficial()]
        return [IsAuthenticated()]

    def get_queryset(self):
        """Officials see every complaint; citizens see only their own."""
        if is_official(self.request.user):
            return Complaint.objects.all()
        return Complaint.objects.filter(owner=self.request.user)

    def perform_create(self, serializer):
        complaint = serializer.save(owner=self.request.user)
        complaint.ref = f"C-{complaint.pk}"      # unique, from the database id
        image_path = complaint.photo.path if complaint.photo else None

        # Earlier originals to compare against, from everyone's reports (the
        # new row has no vectors yet)
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
            logger.exception("Triage failed for complaint %s", complaint.ref)
            complaint.delete()          # do not keep a half-processed complaint
            raise TriageUnavailable()  # for example, when the daily quota is used up

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

            # Start follow-up tracking
            rec = new_record(complaint.ref, complaint.department,
                             complaint.desk, complaint.sla_hours)
            complaint.fu_status = rec["status"]
            complaint.fu_level = rec["level"]
            complaint.fu_window = rec["window"]
            complaint.fu_due_hour = rec["due_hour"]
            complaint.fu_reminded = rec["reminded"]
            complaint.fu_history = rec["history"]
        else:
            complaint.status = Complaint.Status.NEEDS_DETAILS
            complaint.department = result.get("department", "Pending")
            complaint.note = result.get("note", "")

        complaint.save()

    @action(detail=True, methods=["post"])
    def resolve(self, request, pk=None):
        """An official marks the complaint as fixed."""
        complaint = self.get_object()
        if complaint.status != Complaint.Status.ROUTED or complaint.fu_status != "open":
            return Response(
                {"detail": "Only open, routed complaints can be resolved."},
                status=400,
            )
        complaint.fu_status = "resolved"
        complaint.save(update_fields=["fu_status"])
        check(complaint)    # the follow-up graph closes it straight away
        return Response(self.get_serializer(complaint).data)