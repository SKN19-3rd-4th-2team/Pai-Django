# chat/views.py

import json
from django.shortcuts import render, get_object_or_404, redirect
from django.http import StreamingHttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Max

# [주의] login_required 제거함 (비회원 접근 허용을 위해)
from .models import ChatHistory, Chat

# LLM 모듈
from llm_module.main import get_graph_agent
from llm_module.SYSTEM_PROMPT import SYSTEM_PROMPT
from llm_module.memory_utils import convert_db_chats_to_langchain

agent_executor = get_graph_agent()


# =========================================================
# [핵심] 현재 사용자의 히스토리를 가져오는 함수 (회원/비회원 분기)
# =========================================================
def get_current_history(request):
    # 1. 로그인한 회원인 경우
    if request.user.is_authenticated:
        history = (
            ChatHistory.objects.filter(user=request.user)
            .order_by("-created_at")
            .first()
        )
        if not history:
            history = ChatHistory.objects.create(
                user=request.user, order_num=1, description="새로운 대화"
            )
        return history

    # 2. 비회원(Guest)인 경우 -> 세션 ID 사용
    else:
        # 세션 키가 없으면 생성
        if not request.session.session_key:
            request.session.save()

        session_id = request.session.session_key

        # 세션 ID로 조회 (user는 Null인 것만)
        history = (
            ChatHistory.objects.filter(session_id=session_id, user__isnull=True)
            .order_by("-created_at")
            .first()
        )

        if not history:
            history = ChatHistory.objects.create(
                user=None,  # 비회원이므로 Null
                session_id=session_id,
                order_num=1,
                description="게스트 대화",
            )
        return history


# =========================================================
# 뷰: 채팅 화면
# =========================================================
def chat_interface(request):
    user = request.user
    selected_history = None

    # 1. 회원인 경우: 과거 기록을 기억하고 불러옴
    if user.is_authenticated:
        selected_history = (
            ChatHistory.objects.filter(user=user).order_by("-created_at").first()
        )

        if not selected_history:
            selected_history = ChatHistory.objects.create(
                user=user, order_num=1, description="새로운 대화"
            )

    # 2. 비회원인 경우: 접속할 때마다 '무조건' 새로 만듦 (과거 내역 조회 X)
    else:
        # 세션 키 확보 (이건 보안 검증용으로 필수)
        if not request.session.session_key:
            request.session.save()

        session_id = request.session.session_key

        # [핵심] filter().first()로 찾지 않고, 그냥 바로 create() 해버림
        # 이렇게 하면 새로고침 할 때마다 깨끗한 새 방이 열림
        selected_history = ChatHistory.objects.create(
            user=None, session_id=session_id, order_num=1, description="게스트 대화"
        )

    # 3. 선택된(혹은 방금 만든) 방의 대화 내용 가져오기
    # 비회원은 방금 만들었으니 당연히 빈 리스트가 됨 -> 화면 초기화 효과
    chats = Chat.objects.filter(history=selected_history).order_by("order_num")

    # 템플릿에 전달
    current_user_id = user.id if user.is_authenticated else "guest"

    context = {
        "user_id": current_user_id,
        "selected_history_id": selected_history.history_id,
        "chat_history": chats,
    }
    return render(request, "chat/chat_component.html", context)


# =========================================================
# API: 채팅 스트리밍
# =========================================================
@csrf_exempt
def chat_stream_api(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            user_input = data.get("message", "")
            history_id = data.get("history_id")
        except:
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        if not user_input or not history_id:
            return JsonResponse({"error": "Missing data"}, status=400)

        # 1. 히스토리 객체 가져오기 (회원/비회원 분기)
        if request.user.is_authenticated:
            history = get_object_or_404(
                ChatHistory, history_id=history_id, user=request.user
            )
        else:
            if not request.session.session_key:
                return JsonResponse({"error": "Session expired"}, status=403)
            history = get_object_or_404(
                ChatHistory,
                history_id=history_id,
                session_id=request.session.session_key,
            )

        # ------------------------------------------------------------------
        # [순서 관리] 현재 DB의 마지막 순서를 가져와서 기준점으로 삼습니다.
        # ------------------------------------------------------------------
        last_order = history.chats.aggregate(Max("order_num"))["order_num__max"] or 0
        current_save_order = last_order + 1

        # 2. [사용자 메시지 저장]
        user_chat = Chat.objects.create(
            history=history,
            type="HUMAN",
            content=user_input,
            order_num=current_save_order,
        )

        # 다음 메시지(Tool이나 AI)가 저장될 순서 번호 준비
        current_save_order += 1

        # 3. LangChain 메시지 변환 (컨텍스트 로드)
        db_chats = Chat.objects.filter(history=history).order_by("order_num")
        langchain_messages = convert_db_chats_to_langchain(
            db_chats, system_prompt=SYSTEM_PROMPT
        )

        config = {"configurable": {"thread_id": str(history.history_id)}}

        def event_stream():
            # nonlocal을 사용하여 바깥 변수(current_save_order)를 함수 안에서 수정할 수 있게 함
            nonlocal current_save_order

            full_ai_response = ""
            seen_tool_ids = set()

            try:
                # 사용자 메시지 ID 전송 (삭제 버튼용)
                yield json.dumps(
                    {"type": "user_message_id", "chat_id": user_chat.chat_id}
                ) + "\n"

                for msg, metadata in agent_executor.stream(
                    {"messages": langchain_messages},
                    config=config,
                    stream_mode="messages",
                ):
                    curr_node = metadata.get("langgraph_node", "")

                    # (A) AI 텍스트 응답 (스트리밍)
                    if curr_node == "agent" and msg.content:
                        if not msg.tool_calls:
                            full_ai_response += msg.content
                            yield json.dumps(
                                {"type": "token", "content": msg.content}
                            ) + "\n"

                    # (B) 도구 호출 알림 (저장은 생략하고 화면 알림만)
                    if curr_node == "agent" and msg.tool_calls:
                        for tool_call in msg.tool_calls:
                            t_id = tool_call.get("id")
                            t_name = tool_call.get("name")
                            if t_id not in seen_tool_ids:
                                seen_tool_ids.add(t_id)
                                yield json.dumps(
                                    {"type": "tool_call", "tool_name": t_name}
                                ) + "\n"

                    # (C) [핵심 수정] 도구 실행 결과 (TOOLS) -> DB 저장 추가!
                    if curr_node == "tools":
                        content_str = str(msg.content)

                        # 1. 화면에 전송
                        yield json.dumps(
                            {"type": "tool_result", "length": len(content_str)}
                        ) + "\n"

                        # 2. [여기!] DB에 저장
                        # 사용자는 안 보지만 DB에는 기록됨 (type='TOOLS')
                        Chat.objects.create(
                            history=history,
                            type="TOOLS",
                            content=content_str,
                            order_num=current_save_order,
                        )
                        current_save_order += 1  # 순서 증가

                # 4. [AI 최종 답변 DB 저장]
                if full_ai_response:
                    Chat.objects.create(
                        history=history,
                        type="AI",
                        content=full_ai_response,
                        order_num=current_save_order,
                    )
                    # current_save_order += 1 (필요하다면)

            except Exception as e:
                yield json.dumps({"type": "error", "message": str(e)}) + "\n"

        return StreamingHttpResponse(
            event_stream(), content_type="application/x-ndjson"
        )

    return JsonResponse({"error": "Method not allowed"}, status=405)


# =========================================================
# API: 삭제 기능 (비회원 지원)
# =========================================================
@csrf_exempt
def delete_message_api(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            target_chat_id = data.get("message_id")
        except:
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        # 삭제 권한 검증 (회원 vs 비회원)
        try:
            if request.user.is_authenticated:
                target_chat = Chat.objects.get(
                    chat_id=target_chat_id, history__user=request.user
                )
            else:
                target_chat = Chat.objects.get(
                    chat_id=target_chat_id,
                    history__session_id=request.session.session_key,
                    history__user__isnull=True,
                )

            # (이하 삭제 로직 동일)
            history = target_chat.history
            if target_chat.type == "HUMAN":
                start_order = target_chat.order_num
                next_human = (
                    Chat.objects.filter(
                        history=history, type="HUMAN", order_num__gt=start_order
                    )
                    .order_by("order_num")
                    .first()
                )

                if next_human:
                    end_order = next_human.order_num
                    Chat.objects.filter(
                        history=history,
                        order_num__gte=start_order,
                        order_num__lt=end_order,
                    ).delete()
                else:
                    Chat.objects.filter(
                        history=history, order_num__gte=start_order
                    ).delete()

                return JsonResponse({"status": "success"})

            return JsonResponse(
                {"status": "failed", "message": "Can only delete HUMAN messages"}
            )

        except Chat.DoesNotExist:
            return JsonResponse(
                {"status": "failed", "message": "Message not found or unauthorized"}
            )

    return JsonResponse({"error": "Method not allowed"}, status=405)


# =========================================================
# API: 새 대화 (비회원 지원)
# =========================================================
def new_chat(request):
    if request.user.is_authenticated:
        # 회원: 유저 기준 조회
        last_hist = (
            ChatHistory.objects.filter(user=request.user).order_by("-order_num").first()
        )
        new_order = (last_hist.order_num + 1) if last_hist else 1
        ChatHistory.objects.create(
            user=request.user, order_num=new_order, description=f"새 대화 {new_order}"
        )
    else:
        # 비회원: 세션 기준 조회
        if not request.session.session_key:
            request.session.save()
        session_id = request.session.session_key

        last_hist = (
            ChatHistory.objects.filter(session_id=session_id)
            .order_by("-order_num")
            .first()
        )
        new_order = (last_hist.order_num + 1) if last_hist else 1
        ChatHistory.objects.create(
            session_id=session_id,
            user=None,
            order_num=new_order,
            description=f"게스트 대화 {new_order}",
        )

    return redirect("chat:chat_interface")
