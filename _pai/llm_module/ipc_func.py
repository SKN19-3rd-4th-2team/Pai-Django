import os
import numpy as np

# ✅ 상수 설정
MERGE_THRESHOLD_RATIO = 6.64  # 통합 임계값 (비율 %)
TOP_K = 50  # 검색 개수 (Oversampling)
MAX_DISTANCE_THRESHOLD = (
    1.4  # ⛔ 거리 컷오프 (이 값보다 멀면 노이즈로 간주하고 즉시 폐기)
)


def get_ipc_codes_by_query(ipc_model, ipc_collection, query_text, top_k=5):
    """
    단일 쿼리 텍스트를 받아 ChromaDB에서 검색 후,
    1. 거리(Distance) 기반 노이즈 필터링
    2. 계층적 중복 제거(병합)
    를 수행하여 구조화된 리스트를 반환합니다.
    """

    # ---------------------------------------------------------
    # 1. 임베딩 생성
    # ---------------------------------------------------------
    try:
        # ipc_model이 리스트 입력을 기대하므로 리스트로 감싸서 전달
        query_vector = ipc_model([query_text])[0]

        if hasattr(query_vector, "tolist"):
            query_vector = query_vector.tolist()

    except Exception as e:
        print(f"❌ 임베딩 생성 중 오류 발생: {e}")
        return []

    try:
        results = ipc_collection.query(
            query_embeddings=[query_vector],
            n_results=TOP_K,
            # 'kind'가 m(Main Group), 1~5(Subgroup)인 것만 검색
            where={"kind": {"$in": ["m", "1", "2", "3", "4", "5"]}},
            include=["metadatas", "distances"],
        )
    except Exception as e:
        print(f"❌ ChromaDB 검색 중 오류 발생: {e}")
        return []

    if not results["ids"] or not results["ids"][0]:
        return []

    raw_ids = results["ids"][0]
    raw_distances = results["distances"][0]
    raw_metadatas = results["metadatas"][0]


    code_map = {}
    valid_ids = []  # 순서 유지를 위한 리스트

    for code, dist, meta in zip(raw_ids, raw_distances, raw_metadatas):
        if dist > MAX_DISTANCE_THRESHOLD:
            continue

        valid_ids.append(code)
        code_map[code] = {"dist": dist, "meta": meta, "sub": [], "is_absorbed": False}

    # 유효한 결과가 하나도 없으면 빈 리스트 반환
    if not valid_ids:
        return []
    for current_code in valid_ids:
        child_item = code_map[current_code]

        # 이미 흡수된 항목은 패스
        if child_item["is_absorbed"]:
            continue

        path_str = child_item["meta"].get("path", "")
        if not path_str:
            continue

        # 조상 코드 파싱
        ancestors = [
            x.strip() for x in path_str.replace(">", " > ").split(">") if x.strip()
        ]
        if current_code in ancestors:
            ancestors.remove(current_code)

        for parent_code in ancestors:
            if parent_code in code_map:
                parent_item = code_map[parent_code]

                child_dist = child_item["dist"]
                parent_dist = parent_item["dist"]

                if parent_dist > 0:
                    gap = abs(child_dist - parent_dist)
                    ratio = (gap / parent_dist) * 100

                    if ratio <= MERGE_THRESHOLD_RATIO:
                        if parent_code not in child_item["sub"]:
                            child_item["sub"].append(parent_code)

                        # 조상은 흡수 처리 (메인 출력에서 제외)
                        code_map[parent_code]["is_absorbed"] = True

    final_output = []

    for code in valid_ids:
        item = code_map[code]

        if not item["is_absorbed"]:
            entry = {
                "main": code,
                "sub": item["sub"],
                "distance": item["dist"],
            }
            final_output.append(entry)

    return final_output[:top_k]


def get_combined_ipc_codes(ipc_model, ipc_collection, queries, total_top_k=5):
    """
    여러 개의 쿼리 문자열을 받아 통합된 IPC 코드 리스트를 반환합니다.
    (품질 우선 라운드 로빈 + 형제 노드 중복 제거 적용)
    """

    # 1. 쿼리별 결과 수집 및 그룹 품질 평가
    query_groups = []

    for query in queries:
        raw_results = get_ipc_codes_by_query(ipc_model, ipc_collection, query, top_k=total_top_k * 10)

        if not raw_results:
            continue

        # 그룹 품질 점수 계산
        top_n_check = min(len(raw_results), 3)
        avg_dist = (
            sum(item["distance"] for item in raw_results[:top_n_check]) / top_n_check
        )

        for item in raw_results:
            item["source_query"] = query

        query_groups.append(
            {
                "query": query,
                "avg_dist": avg_dist,
                "queue": raw_results, 
            }
        )

    if not query_groups:
        return []

    # 2. 그룹 정렬 (품질 순)
    query_groups.sort(key=lambda x: x["avg_dist"])

    final_list = []
    
    # [중복 방지용 집합]
    inserted_main_codes = set()   # 이미 선택된 메인 코드 (완전 중복 방지)
    inserted_parents = set()      # 이미 선택된 코드들의 부모들 (형제 중복 방지)

    # 3. 라운드 로빈으로 추출
    while len(final_list) < total_top_k:
        added_in_this_round = False

        for group in query_groups:
            if len(final_list) >= total_top_k:
                break

            if group["queue"]:
                # 큐에서 가장 좋은 후보(1등)를 꺼냄
                candidate = group["queue"].pop(0)

                # -----------------------------------------------------------
                # [Filter 1] 완전 중복 체크 (이미 리스트에 있는 코드인가?)
                # -----------------------------------------------------------
                if candidate["main"] in inserted_main_codes:
                    continue

                # -----------------------------------------------------------
                # [Filter 2] 형제 중복 체크 (부모가 같은가?)
                # -----------------------------------------------------------
                # 이미 등록된 부모 집합(inserted_parents)에 내 부모가 포함되어 있다면,
                # "내 형제가 이미 등록되었다"는 뜻이므로 나는 스킵함.
                # (큐가 거리순 정렬되어 있으므로, 먼저 등록된 형제가 더 좋은 형제임)
                is_sibling = False
                for parent in candidate["sub"]:
                    if parent in inserted_parents:
                        is_sibling = True
                        break
                
                if is_sibling:
                    continue 

                # -----------------------------------------------------------
                # [Pass] 통과! 리스트에 추가
                # -----------------------------------------------------------
                final_list.append(candidate)
                
                # 방문 처리
                inserted_main_codes.add(candidate["main"])
                
                # 내 부모들도 '사용됨'으로 등록 -> 이후에 나올 내 형제들을 막음
                for parent in candidate["sub"]:
                    inserted_parents.add(parent)
                
                added_in_this_round = True

        if not added_in_this_round:
            break

    return final_list


def get_ipc_detail_data_from_code(ipc_collection, codes):
    results = ipc_collection.get(ids=list(codes))
    
    found_ids = results.get("ids", [])
    found_docs = results.get("documents", [])
    found_metas = results.get("metadatas", [])
    
    returns = []
    for i in range(len(found_ids)):
        meta = found_metas[i] if found_metas and i < len(found_metas) else {}
        
        temp = {
            "ids": found_ids[i], 
            "description": found_docs[i], 
            "type": meta.get('kind', ''), 
            "ancestors": meta.get('path', '')
        }
        returns.append(temp)
    return returns

def get_ipc_description_from_code(ipc_collection, codes):
    results = ipc_collection.get(ids=list(codes))
    
    found_ids = results.get("ids", [])
    found_docs = results.get("documents", [])
    
    returns = []
    for i in range(len(found_ids)):
        temp = {
            "ids": found_ids[i], 
            "description": found_docs[i]
        }
        returns.append(temp)
    return returns


def search_ipc_with_query(ipc_model, ipc_collection, queries, top_k=5):
    search_output = get_combined_ipc_codes(ipc_model, ipc_collection, queries, top_k)
    temp_codes = {"mains": [], "subs": []}
    for i in search_output:
        temp_codes["mains"].append(i.get("main"))
        if len(i.get("sub")) > 0:
            for ii in i.get("sub"):
                temp_codes["subs"].append(ii)
    returns = {
        "mains": get_ipc_description_from_code(ipc_collection,set(temp_codes["mains"])),
        "subs": get_ipc_description_from_code(ipc_collection,set(temp_codes["subs"])),
    }
    return returns