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
    """
    전체 채팅 페이지 렌더링
    """
    user = request.user
    selected_history = None

    # 1. 채팅 목록 가져오기 (정렬 기준 변경: created_at -> order_num)
    if user.is_authenticated:
        # [수정] order_num 내림차순 정렬 (높은 번호가 위로)
        history_list = ChatHistory.objects.filter(user=user).order_by("-order_num")
    else:
        # 비회원 세션 처리
        if not request.session.session_key:
            request.session.save()
        session_id = request.session.session_key

        # [수정] order_num 내림차순 정렬
        history_list = ChatHistory.objects.filter(
            session_id=session_id, user__isnull=True
        ).order_by("-order_num")

    # 2. 특정 채팅방 선택 로직 (URL 파라미터 ?history_id=123)
    target_id = request.GET.get("history_id")

    if target_id:
        selected_history = history_list.filter(history_id=target_id).first()

    # 3. 선택된 게 없으면 -> 목록의 첫 번째(가장 높은 번호) 선택 or 새로 생성
    if not selected_history:
        if history_list.exists():
            selected_history = history_list.first()
        else:
            # 기록이 없으면 새 방 생성 (1번방)
            if user.is_authenticated:
                selected_history = ChatHistory.objects.create(
                    user=user, order_num=1, description="새로운 대화"
                )
            else:
                session_id = request.session.session_key
                selected_history = ChatHistory.objects.create(
                    session_id=session_id,
                    user=None,
                    order_num=1,
                    description="게스트 대화",
                )

            # (참고) 방금 만든 방은 쿼리셋 재평가 시 자동으로 반영됨

    # 4. 선택된 방의 대화 내용 가져오기 (대화 내용은 순서대로 1,2,3...)
    chats = Chat.objects.filter(history=selected_history).order_by("order_num")

    context = {
        "user_id": user.id if user.is_authenticated else "guest",
        "selected_history_id": selected_history.history_id,
        "chat_history": chats,
        "history_list": history_list,
    }

    return render(request, "chat/chat_interface.html", context)


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
    """
    새 대화방 생성 함수 (시간 기준 판단 + 재활용 시 최상단 이동)
    1. '가장 최근에 생성된(created_at)' 방을 찾습니다.
    2. 그 방이 비어있으면 -> 그 방의 순서(order)를 1등으로 높이고 재활용합니다.
    3. 그 방에 대화가 있으면 -> 진짜 새 방을 만들고 순서를 1등으로 줍니다.
    """

    user = request.user
    target_history_qs = None  # 쿼리셋을 담을 변수

    # 1. 대상 쿼리셋 설정 (회원/비회원 분기)
    if user.is_authenticated:
        target_history_qs = ChatHistory.objects.filter(user=user)
    else:
        if not request.session.session_key:
            request.session.save()
        session_id = request.session.session_key
        target_history_qs = ChatHistory.objects.filter(session_id=session_id)

    # 2. [판단 기준] 가장 최근에 '생성된' 방 찾기 (order 기준 아님!)
    last_created_hist = target_history_qs.order_by("-created_at").first()

    # 3. [순서 결정] 현재 존재하는 방들 중 가장 높은 order 번호 찾기
    # (새로 만들거나, 기존 방을 위로 올릴 때 이 번호보다 커야 함)
    current_max_order = (
        target_history_qs.aggregate(Max("order_num"))["order_num__max"] or 0
    )
    new_top_order = current_max_order + 1

    # 4. 로직 수행
    if last_created_hist and not last_created_hist.chats.exists():
        # A. 최근 방이 있는데, 텅 비어있다 -> "재활용 + 맨 위로 이동"

        # 이미 맨 위라면(순서가 max라면) 굳이 업데이트 안 해도 됨
        if last_created_hist.order_num < current_max_order:
            last_created_hist.order_num = new_top_order
            last_created_hist.save()

        # 해당 방으로 이동
        return redirect("chat:chat_interface")

    else:
        # B. 최근 방에 대화가 있거나, 방이 아예 없다 -> "새 방 생성"
        if user.is_authenticated:
            ChatHistory.objects.create(
                user=user,
                order_num=new_top_order,
                description=f"새 대화 {new_top_order}",
            )
        else:
            # 비회원
            ChatHistory.objects.create(
                session_id=request.session.session_key,
                user=None,
                order_num=new_top_order,
                description=f"게스트 대화 {new_top_order}",
            )

    return redirect("chat:chat_interface")


# =========================================================
# API: 채팅방 순서 변경 (Drag & Drop 결과 저장)
# =========================================================
@csrf_exempt
def update_history_order(request):
    """
    프론트엔드에서 [id_A, id_B, id_C] 순서로 ID 리스트를 보내면,
    DB의 order_num을 업데이트하여 순서를 고정합니다.
    """
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            ordered_ids = data.get("ordered_ids", [])

            # 목록의 길이 (예: 10개면 10부터 시작해서 감소)
            # 우리는 order_by('-order_num') 이므로, 숫자가 클수록 위에 뜸
            total_count = len(ordered_ids)

            for index, hist_id in enumerate(ordered_ids):
                # 순서대로 점수 부여 (1등에게 가장 높은 숫자)
                new_order = total_count - index
                ChatHistory.objects.filter(
                    history_id=hist_id, user=request.user
                ).update(order_num=new_order)

            return JsonResponse({"status": "success"})
        except Exception as e:
            return JsonResponse({"status": "error", "message": str(e)})

    return JsonResponse({"error": "Method not allowed"}, status=405)


# =========================================================
# API: 채팅방 삭제 (목록에서 삭제)
# =========================================================
@csrf_exempt
def delete_history_api(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            history_id = data.get("history_id")

            # 본인 것인지 확인 후 삭제
            ChatHistory.objects.filter(
                history_id=history_id, user=request.user
            ).delete()

            return JsonResponse({"status": "success"})
        except:
            return JsonResponse({"status": "error", "message": "Failed to delete"})

    return JsonResponse({"error": "Method not allowed"}, status=405)
