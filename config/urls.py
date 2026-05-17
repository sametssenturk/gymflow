from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from core.views import home
from dashboard.views import DemoDashboardView

admin.site.site_header = "GymFlow Yönetim Paneli"
admin.site.site_title = "GymFlow Yönetim Paneli"
admin.site.index_title = "Sistem Yönetimi"

urlpatterns = [
    path("", home, name="home"),
    path("demo-dashboard/", DemoDashboardView.as_view(), name="demo_dashboard"),
    path("admin/", admin.site.urls),
    path("accounts/", include("accounts.urls")),
    path("dashboard/", include("dashboard.urls")),
    path("members/", include("members.urls")),
    path("payments/", include("payments.urls")),
    path("packages/", include("memberships.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
