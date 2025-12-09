# llm_module/memory_utils.py

from langchain_core.messages import HumanMessage, SystemMessage, AIMessage, ToolMessage


def convert_session_to_langchain_messages(session_history, system_prompt: str = None):
    """
    [조립]
    DB/Session(리스트+딕셔너리) -> LangChain Message 객체 리스트로 변환
    """
    messages = []

    # 1. 시스템 프롬프트가 있다면 맨 앞에 추가
    if system_prompt:
        messages.append(SystemMessage(content=system_prompt))

    # 2. 히스토리 순회하며 객체로 변환
    for msg in session_history:
        role = msg.get("role")
        content = msg.get("content")

        if role == "user":
            messages.append(HumanMessage(content=content))
        elif role == "assistant":
            messages.append(AIMessage(content=content))
        # tool 메시지 등은 필요시 추가 구현

    return messages


def convert_langchain_message_to_dict(message):
    """
    [분해]
    LangChain Message 객체 -> DB/Session 저장용 딕셔너리로 변환
    (주로 AI의 최종 응답을 저장할 때 사용)
    """
    if isinstance(message, HumanMessage):
        return {"role": "user", "content": message.content}
    elif isinstance(message, AIMessage):
        return {"role": "assistant", "content": message.content}
    elif isinstance(message, SystemMessage):
        return {"role": "system", "content": message.content}
    else:
        # ToolMessage 등 기타
        return {"role": "tool", "content": str(message.content)}
