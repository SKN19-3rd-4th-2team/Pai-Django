from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, logout, login as auth_login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth import update_session_auth_hash

from .forms import SignupForm, LoginForm, ProfileUpdateForm


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
            return redirect("chat:chat_interface")  # chat 페이지로 이동.

    else:
        form = LoginForm()

    return render(request, "account/login.html", {"form": form})

# 회원탈퇴 페이지
def withdraw(request):
    return render(request, "account/withdraw.html")


# 회원탈퇴
@login_required
def withdraw_final(request):
    if request.method == "POST":
        user = request.user
        logout(request)        # 세션 로그아웃
        user.delete()          # DB에서 삭제
        return redirect("main:index") 
    return redirect("account:mypage")  # POST가 아니면 마이페이지로


# 로그아웃
@login_required
def logout_view(request):
    """
    로그아웃 처리:
    1. 현재 사용자의 세션 데이터를 삭제합니다 (DB의 django_session 테이블에서 제거).
    2. 브라우저의 sessionid 쿠키도 무효화됩니다.
    3. 메인 페이지로 이동합니다.
    """
    logout(request)
    return redirect("main:index")  # 메인 페이지로 이동


@login_required
def myinfo(request):
    """
    마이페이지:
    - 현재 로그인한 사용자 정보 표시
    - 별명(닉네임) 변경
    - 비밀번호 변경
    """
    user = request.user
    success_message = ""

    # 기본 폼 생성 (GET일 때 사용)
    profile_form = ProfileUpdateForm(user=user)
    password_form = PasswordChangeForm(user)

    if request.method == "POST":
        # 어떤 버튼이 눌렸는지 name으로 구분
        if "profile_submit" in request.POST:
            # 별명 수정 폼
            profile_form = ProfileUpdateForm(request.POST, user=user)
            if profile_form.is_valid():
                profile_form.save()
                success_message = "별명이 성공적으로 변경되었습니다."

        elif "password_submit" in request.POST:
            # 비밀번호 변경 폼
            password_form = PasswordChangeForm(user, request.POST)
            if password_form.is_valid():
                changed_user = password_form.save()
                # 비밀번호를 바꿔도 로그인 풀리지 않게 세션 유지
                update_session_auth_hash(request, changed_user)
                success_message = "비밀번호가 성공적으로 변경되었습니다."

    context = {
        "user_obj": user,
        "profile_form": profile_form,
        "password_form": password_form,
        "success_message": success_message,
    }
    return render(request, "account/myinfo.html", context)
