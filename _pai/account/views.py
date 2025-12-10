from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, logout, login as auth_login

# from django.contrib.auth import logout as auth_logout

from django.http import HttpResponse

from .forms import SignupForm, LoginForm

# 수정 부분: signup(), login()


# 회원가입
def signup(request):
    if request.method == "POST":
        form = SignupForm(request.POST)

        if form.is_valid():
            user = form.save()  # User 모델에 저장됨 (비밀번호 자동 암호화. sha256)
            nickname = form.cleaned_data.get("nickname")

            return render(
                request, "account/signup_success.html", {"username": nickname}
            )  # 회원가입 성공 시 success 화면으로 이동

    else:
        form = SignupForm()

    return render(request, "account/signup.html", {"form": form})


# 로그인
def login(request):
    if request.method == "POST":
        form = LoginForm(
            request, data=request.POST
        )  # 비밀번호 일치 여부 등을 여기서 모두 django가 확인

        if form.is_valid():  # 유효성 검증 통과 시
            user = form.get_user()
            auth_login(request, user)  # 로그인 처리
            return redirect("chat:chat_interface")  # chat 페이지로 이동. 수정 부분

    else:
        form = LoginForm()

    return render(request, "account/login.html", {"form": form})


# 로그아웃 (버튼 추가 후)
# def logout(request):
#     auth_logout(request)
#     return redirect("")


def chat(request):
    return render(request, "account/chat.html")


def withdraw(request):
    return render(request, "account/withdraw.html")


def myinfo(request):
    context = {
        "user_id": "FantAstIc5",
        "password": "@@FantAstIc5",
        "nickname": "판타스틱오",
        "message": "변경이 완료되었습니다.",
    }
    return render(request, "account/myinfo.html", context)


def logout_view(request):
    """
    로그아웃 처리:
    1. 현재 사용자의 세션 데이터를 삭제합니다 (DB의 django_session 테이블에서 제거).
    2. 브라우저의 sessionid 쿠키도 무효화됩니다.
    3. 로그인 페이지로 튕겨냅니다.
    """
    logout(request)
    return redirect("account:login")  # 로그인 페이지로 이동
