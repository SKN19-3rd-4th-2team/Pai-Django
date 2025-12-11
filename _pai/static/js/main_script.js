// 스크롤 모션 효과 제거됨 - 일반 스크롤 사용
document.addEventListener('DOMContentLoaded', function () {
    // 페이지 로드 시 feature 카드들을 바로 표시
    const cards = document.querySelectorAll('.feature-card');
    cards.forEach(card => {
        card.classList.add('show');
    });
});