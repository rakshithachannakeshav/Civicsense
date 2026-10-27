from django.urls import path
from rest_framework.routers import DefaultRouter

from .auth_views import LoginView, LogoutView, MeView, RegisterView
from .views import ComplaintViewSet

router = DefaultRouter()
router.register("complaints", ComplaintViewSet)

urlpatterns = [
    path("auth/register/", RegisterView.as_view()),
    path("auth/login/", LoginView.as_view()),
    path("auth/logout/", LogoutView.as_view()),
    path("auth/me/", MeView.as_view()),
] + router.urls
