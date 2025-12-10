# llm_module/memory_utils.py

from langchain_core.messages import HumanMessage, SystemMessage, AIMessage, ToolMessage


# llm_module/memory_utils.py

from langchain_core.messages import HumanMessage, SystemMessage, AIMessage, ToolMessage


def convert_db_chats_to_langchain(db_chats, system_prompt: str = None):
    """
    [조립]
    DB QuerySet (Chat 모델 리스트) -> LangChain Message 객체 리스트로 변환
    """
    messages = []

    # 1. 시스템 프롬프트 추가
    if system_prompt:
        messages.append(SystemMessage(content=system_prompt))

    # 2. DB 데이터 순회
    for chat in db_chats:
        if chat.type == "HUMAN":
            messages.append(HumanMessage(content=chat.content))
        elif chat.type == "AI":
            messages.append(AIMessage(content=chat.content))
        # ToolMessage는 필요 시 추가 (현재는 필터링됨)

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
