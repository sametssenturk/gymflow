from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


User = get_user_model()


class HomePageTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="admin",
            password="StrongPass123",
            role=User.Role.ADMIN,
        )

    def test_home_page_has_customer_facing_copy(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Üyelik ve tahsilat takibini tek ekranda toplayın.",
        )
        self.assertContains(response, "Hemen Giriş Yap")
        self.assertContains(response, "Özellikleri İncele")
        self.assertContains(response, "Yaklaşan üyelik bitişlerini erken fark edin")
        self.assertContains(response, "Paket takibi")
        self.assertContains(
            response,
            "Kontrol paneli, üyeler, paketler, ödemeler ve istatistikler aynı tasarım diliyle ilerler.",
        )
        self.assertContains(response, "Demo Görünümü Aç")
        self.assertContains(
            response,
            "Giriş yapmadan örnek panel deneyimini inceleyin.",
        )
        self.assertContains(response, "Panel özeti")
        self.assertContains(response, "Salonun güncel durumunu tek bakışta görün")
        self.assertContains(response, "Son 7 günün tahsilatı")
        self.assertContains(response, "Takip listesi")

    def test_authenticated_users_are_redirected_to_dashboard(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("dashboard:index"))

    def test_preview_route_is_removed(self):
        self.client.force_login(self.admin)
        response = self.client.get("/preview/")
        self.assertEqual(response.status_code, 404)
