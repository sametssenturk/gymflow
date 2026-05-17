import os
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from members.models import Member


User = get_user_model()


class AuthFlowTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username="admin",
            password="StrongPass123",
            role=User.Role.ADMIN,
        )

    def test_admin_role_sets_staff_flag(self):
        self.assertTrue(self.user.is_staff)

    def test_legacy_staff_role_is_rejected_on_login(self):
        User.objects.filter(pk=self.user.pk).update(role="STAFF", is_staff=False)
        response = self.client.post(
            reverse("accounts:login"),
            {"username": "admin", "password": "StrongPass123"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Yalnızca yönetici hesabıyla giriş yapılabilir.")

    def test_login_page_renders(self):
        response = self.client.get(reverse("accounts:login"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Panel erişimi")
        self.assertContains(response, "Yöneticiler için güvenli erişim")
        self.assertNotContains(response, "çalışan")
        self.assertContains(response, "Ana sayfa")
        self.assertContains(response, "Demo Görünüm")
        self.assertNotContains(response, "Özellikler")
        self.assertNotContains(response, "Günlük Akış")

    def test_login_redirects_to_dashboard(self):
        response = self.client.post(
            reverse("accounts:login"),
            {"username": "admin", "password": "StrongPass123"},
        )
        self.assertRedirects(response, reverse("dashboard:index"), fetch_redirect_response=False)

    def test_login_is_throttled_after_repeated_failures(self):
        for _ in range(5):
            response = self.client.post(
                reverse("accounts:login"),
                {"username": "admin", "password": "WrongPass123"},
            )
            self.assertEqual(response.status_code, 200)

        locked_response = self.client.post(
            reverse("accounts:login"),
            {"username": "admin", "password": "StrongPass123"},
        )
        self.assertEqual(locked_response.status_code, 200)
        self.assertContains(
            locked_response,
            "Çok sayıda hatalı giriş denemesi yapıldı. Lütfen 15 dakika sonra tekrar deneyin.",
        )

    def test_demo_login_can_refresh_portfolio_dataset(self):
        Member.objects.create(
            first_name="Legacy",
            last_name="Record",
            email="legacy@example.com",
        )

        with patch.dict(
            os.environ,
            {
                "PORTFOLIO_DEMO_RESET_ON_LOGIN": "1",
                "PORTFOLIO_DEMO_USERNAME": "admin",
                "PORTFOLIO_DEMO_MEMBER_COUNT": "6",
                "PORTFOLIO_DEMO_RESET_ALL_DATA": "1",
            },
            clear=False,
        ):
            response = self.client.post(
                reverse("accounts:login"),
                {"username": "admin", "password": "StrongPass123"},
                follow=True,
            )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Member.objects.filter(email="legacy@example.com").exists())
        self.assertEqual(Member.objects.filter(email__endswith="@gymflow.local").count(), 6)
        self.assertContains(response, "Demo veri seti yenilendi.")

    def test_logout_redirects_home(self):
        self.client.login(username="admin", password="StrongPass123")
        response = self.client.post(reverse("accounts:logout"))
        self.assertRedirects(response, reverse("home"), fetch_redirect_response=False)
