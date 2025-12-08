document.addEventListener('DOMContentLoaded', function () {
    const wrapper = document.querySelector('.snap-wrapper');
    const sections = document.querySelectorAll('.full-section');
    let currentSectionIndex = 0;
    let isScrolling = false;

    // 초기 로딩 시 첫 번째 섹션이 features라면 애니메이션 실행 (혹시 모를 상황 대비)
    if (currentSectionIndex === 1) {
        animateCards();
    }

    window.addEventListener('wheel', function (e) {
        e.preventDefault();

        if (isScrolling) return;

        if (e.deltaY > 0) {
            if (currentSectionIndex < sections.length - 1) {
                moveSection(currentSectionIndex + 1);
            }
        } else {
            if (currentSectionIndex > 0) {
                moveSection(currentSectionIndex - 1);
            }
        }
    }, { passive: false });

    function moveSection(index) {
        isScrolling = true;
        currentSectionIndex = index;

        sections[index].scrollIntoView({
            behavior: 'smooth',
            block: 'start'
        });

        // [추가된 부분] 만약 Features 섹션(index 1)에 도달하면 카드 애니메이션 시작
        if (index === 1) {
            animateCards();
        } else {
            // (선택사항) 다른 페이지로 가면 다시 숨길지 결정
            // 다시 숨겨야 나중에 또 애니메이션이 나옴. 싫으면 이 else문 삭제.
            resetCards();
        }

        setTimeout(() => {
            isScrolling = false;
        }, 800);
    }

    // [카드 애니메이션 함수]
    function animateCards() {
        const cards = document.querySelectorAll('.feature-card');

        cards.forEach((card, i) => {
            // setTimeout을 사용해 하나씩 시간차를 두고 실행 (0.2초 간격)
            setTimeout(() => {
                card.classList.add('show');
            }, i * 500); // 0ms, 200ms, 400ms 순서로 실행됨
        });
    }

    // [카드 초기화 함수] 다른 섹션으로 가면 다시 숨김
    function resetCards() {
        const cards = document.querySelectorAll('.feature-card');
        cards.forEach(card => {
            card.classList.remove('show');
        });
    }
});