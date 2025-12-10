from django.urls import path
from account import views

app_name = "account"

urlpatterns = [
    path("login/", views.login, name="login"),
    # accounts로 이동하면 바로 login 페이지 나오는 구조. -> 수정 필요성?
    path("signup/", views.signup, name="signup"),
    # path("chat/", views.chat, name="chat"), # 수정 부분
    path("withdraw/", views.withdraw, name="withdraw"),
    path("myinfo/", views.myinfo, name="myinfo"),
    path("logout/", views.logout_view, name="logout"),
]
