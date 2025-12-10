from django.urls import path
from account import views

app_name = "account"

urlpatterns = [
    path("login/", views.login, name="login"),
    path("signup/", views.signup, name="signup"),
    path("withdraw/", views.withdraw, name="withdraw"),
    path("withdraw_final/", views.withdraw_final, name="withdraw_final"),
    path("myinfo/", views.myinfo, name="myinfo"),
    path("logout/", views.logout_view, name="logout"),
]
