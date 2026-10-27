from django.contrib import admin

from .models import Complaint


@admin.register(Complaint)
class ComplaintAdmin(admin.ModelAdmin):
    list_display = ("ref", "category", "severity", "status", "department", "fu_status", "owner", "created_at")
    list_filter = ("status", "category", "severity", "fu_status")
    search_fields = ("ref", "text", "location")
    exclude = ("desc_vec", "loc_vec")
