from django.conf import settings
from rest_framework.permissions import BasePermission


def is_official(user):
    """Officials are members of the 'officials' group (or superusers)."""
    if not user or not user.is_authenticated:
        return False
    return user.is_superuser or user.groups.filter(name=settings.OFFICIALS_GROUP).exists()


class IsOfficial(BasePermission):
    message = "Only department officials can do this."

    def has_permission(self, request, view):
        return is_official(request.user)
