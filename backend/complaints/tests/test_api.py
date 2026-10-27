import io
import shutil
import tempfile
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from PIL import Image
from rest_framework.test import APITestCase

from complaints.models import Complaint

from .helpers import OfflineAgentsMixin

User = get_user_model()
TEMP_MEDIA = tempfile.mkdtemp()


def png_file(name="photo.png"):
    buf = io.BytesIO()
    Image.new("RGB", (4, 4), "grey").save(buf, "PNG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")


@override_settings(MEDIA_ROOT=TEMP_MEDIA,
                   EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
                   PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])  # fast tests
class ApiTestCase(OfflineAgentsMixin, APITestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEMP_MEDIA, ignore_errors=True)

    def setUp(self):
        super().setUp()
        self.asha = User.objects.create_user("asha", "asha@example.org", "pw-12345-xyz")
        self.ravi = User.objects.create_user("ravi", "ravi@example.org", "pw-12345-xyz")
        self.officer = User.objects.create_user("officer", "off@example.org", "pw-12345-xyz")
        self.officer.groups.add(Group.objects.get(name="officials"))

    def as_user(self, user):
        self.client.force_authenticate(user)

    def file(self, text="Deep pothole near the school gate", location="5th Cross, Jayanagar", **extra):
        self.as_user(self.asha)
        return self.client.post("/api/complaints/", {"text": text, "location": location, **extra},
                                format="multipart")


class AuthTests(ApiTestCase):
    def test_anonymous_cannot_use_complaints(self):
        self.assertEqual(self.client.get("/api/complaints/").status_code, 401)
        self.assertEqual(self.client.post("/api/complaints/", {"text": "x"}).status_code, 401)

    def test_register_login_me_logout(self):
        res = self.client.post("/api/auth/register/",
                               {"username": "meera", "password": "a-Good-pass-987", "email": "m@example.org"})
        self.assertEqual(res.status_code, 201)
        self.assertFalse(res.data["user"]["is_official"])
        token = res.data["token"]

        res = self.client.post("/api/auth/login/", {"username": "meera", "password": "a-Good-pass-987"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["token"], token)

        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token}")
        self.assertEqual(self.client.get("/api/auth/me/").data["username"], "meera")
        self.assertEqual(self.client.post("/api/auth/logout/").status_code, 204)
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 401)

    def test_register_rejects_weak_password_and_duplicate_name(self):
        weak = self.client.post("/api/auth/register/", {"username": "x1", "password": "123"})
        self.assertEqual(weak.status_code, 400)
        dup = self.client.post("/api/auth/register/", {"username": "ASHA", "password": "a-Good-pass-987"})
        self.assertEqual(dup.status_code, 400)

    def test_wrong_password_is_rejected(self):
        res = self.client.post("/api/auth/login/", {"username": "asha", "password": "nope"})
        self.assertEqual(res.status_code, 400)

    def test_registering_never_makes_an_official(self):
        res = self.client.post("/api/auth/register/",
                               {"username": "sneaky", "password": "a-Good-pass-987", "is_official": True})
        self.assertFalse(res.data["user"]["is_official"])

    def test_official_flag_reported_on_login(self):
        res = self.client.post("/api/auth/login/", {"username": "officer", "password": "pw-12345-xyz"})
        self.assertTrue(res.data["user"]["is_official"])


class ComplaintApiTests(ApiTestCase):
    def test_create_routes_and_records_the_owner(self):
        res = self.file()
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(res.data["status"], "routed")
        self.assertEqual(res.data["ref"], f"C-{res.data['id']}")
        self.assertEqual(res.data["fu_status"], "open")
        self.assertEqual(res.data["submitted_by"], "asha")
        self.assertNotIn("desc_vec", res.data)
        self.assertNotIn("owner", res.data)
        self.assertEqual(Complaint.objects.get(pk=res.data["id"]).owner, self.asha)

    def test_photo_upload_is_accepted(self):
        res = self.file(photo=png_file())
        self.assertEqual(res.status_code, 201, res.data)
        self.assertTrue(res.data["photo"])

    def test_unclear_complaint_needs_details(self):
        res = self.file(text="something is wrong here", location="unknown")
        self.assertEqual(res.data["status"], "needs_details")
        self.assertEqual(res.data["letter"], "")

    def test_second_report_of_same_problem_is_a_duplicate(self):
        first = self.file("Deep pothole near the school gate", "5th Cross, Jayanagar 4th Block")
        self.as_user(self.ravi)
        second = self.client.post("/api/complaints/", {
            "text": "Deep pothole near the school gate", "location": "5th Cross, Jayanagar 4th Block"})
        self.assertEqual(second.data["status"], "duplicate")
        self.assertEqual(second.data["duplicate_of"], first.data["ref"])

    def test_triage_failure_returns_503_and_leaves_no_row(self):
        self.as_user(self.asha)
        with mock.patch("complaints.views.process_complaint", side_effect=RuntimeError("quota")), \
                self.assertLogs("complaints.views", level="ERROR"):
            res = self.client.post("/api/complaints/", {"text": "pothole", "location": "x"})
        self.assertEqual(res.status_code, 503)
        self.assertEqual(Complaint.objects.count(), 0)

    def test_citizen_sees_only_own_complaints(self):
        mine = self.file("Garbage not collected for four days", "Block A")
        self.as_user(self.ravi)
        self.client.post("/api/complaints/", {"text": "Street lamp not working", "location": "Block B"})

        self.as_user(self.asha)
        listing = self.client.get("/api/complaints/")
        self.assertEqual([c["id"] for c in listing.data], [mine.data["id"]])

    def test_citizen_cannot_open_someone_elses_complaint(self):
        theirs = self.file()
        self.as_user(self.ravi)
        self.assertEqual(self.client.get(f"/api/complaints/{theirs.data['id']}/").status_code, 404)

    def test_official_sees_everything(self):
        self.file("Garbage not collected for four days", "Block A")
        self.as_user(self.ravi)
        self.client.post("/api/complaints/", {"text": "Street lamp not working", "location": "Block B"})
        self.as_user(self.officer)
        self.assertEqual(len(self.client.get("/api/complaints/").data), 2)


class ResolveTests(ApiTestCase):
    def test_citizen_cannot_resolve(self):
        c = self.file()
        res = self.client.post(f"/api/complaints/{c.data['id']}/resolve/")
        self.assertEqual(res.status_code, 403)
        self.assertEqual(Complaint.objects.get(pk=c.data["id"]).fu_status, "open")

    def test_official_resolves_and_citizen_is_emailed(self):
        c = self.file()
        self.as_user(self.officer)
        res = self.client.post(f"/api/complaints/{c.data['id']}/resolve/")
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data["fu_status"], "closed")
        self.assertIn("Resolved", res.data["fu_history"][-1])
        self.assertEqual(mail.outbox[-1].to, ["asha@example.org"])

    def test_cannot_resolve_twice_or_a_duplicate(self):
        c = self.file()
        self.as_user(self.officer)
        self.client.post(f"/api/complaints/{c.data['id']}/resolve/")
        again = self.client.post(f"/api/complaints/{c.data['id']}/resolve/")
        self.assertEqual(again.status_code, 400)

        self.as_user(self.ravi)
        dup = self.client.post("/api/complaints/", {"text": "Deep pothole near the school gate",
                                                    "location": "5th Cross, Jayanagar"})
        self.as_user(self.officer)
        self.assertEqual(self.client.post(f"/api/complaints/{dup.data['id']}/resolve/").status_code, 400)
