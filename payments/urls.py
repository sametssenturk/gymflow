from django.urls import path

from payments.views import PaymentCreateView, PaymentDeleteView, PaymentListView, PaymentUpdateView

app_name = "payments"

urlpatterns = [
    path("", PaymentListView.as_view(), name="list"),
    path("add/", PaymentCreateView.as_view(), name="add"),
    path("<int:pk>/edit/", PaymentUpdateView.as_view(), name="edit"),
    path("<int:pk>/delete/", PaymentDeleteView.as_view(), name="delete"),
]
