import os

from django.contrib import messages
from django.contrib.auth.views import LoginView, LogoutView
from django.urls import reverse_lazy

from accounts.forms import AdminAuthenticationForm
from dashboard.demo_seed import seed_demo_data


TRUTHY_VALUES = {"1", "true", "yes", "on"}


class AppLoginView(LoginView):
    template_name = "accounts/login.html"
    redirect_authenticated_user = True
    authentication_form = AdminAuthenticationForm

    def form_valid(self, form):
        user = form.get_user()
        reset_on_login = os.getenv("PORTFOLIO_DEMO_RESET_ON_LOGIN", "0").lower() in TRUTHY_VALUES
        demo_username = os.getenv("PORTFOLIO_DEMO_USERNAME", "")
        should_refresh_demo = reset_on_login and (not demo_username or user.username == demo_username)
        if should_refresh_demo:
            demo_member_count = int(os.getenv("PORTFOLIO_DEMO_MEMBER_COUNT", "160"))
            reset_all_data = os.getenv("PORTFOLIO_DEMO_RESET_ALL_DATA", "0").lower() in TRUTHY_VALUES
            preserve_plans = os.getenv("PORTFOLIO_DEMO_PRESERVE_PLANS", "0").lower() in TRUTHY_VALUES
            seed_demo_data(
                total_members=demo_member_count,
                reset_all_data=reset_all_data,
                preserve_plans=preserve_plans,
            )
            messages.info(self.request, "Demo veri seti yenilendi.")
        return super().form_valid(form)

    def get_success_url(self):
        return self.get_redirect_url() or reverse_lazy("dashboard:index")


class AppLogoutView(LogoutView):
    next_page = reverse_lazy("home")
