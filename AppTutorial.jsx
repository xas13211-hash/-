import React, { useState, useEffect } from 'react';

export default function AppTutorial({ run, onFinish, currentTab }) {
    const [stepIndex, setStepIndex] = useState(0);

    const steps = [
        // [0] 시작: AI 에이전트 화면 (App.jsx 초기값이 chat이므로 여기서 시작)
        {
            title: "🎉 환영합니다!",
            desc: "이곳은 **AI 에이전트(메인 챗봇)** 화면입니다.\n여기서 AI와 대화하며 전략을 수립할 수 있습니다.",
            style: { top: '50%', left: '50%', transform: 'translate(-50%, -50%)' },
            arrow: null,
            waitForTab: null
        },
        // [1] 차트로 이동 미션
        {
            title: "미션 1: 차트 메뉴 클릭",
            desc: "왼쪽 사이드바의 **'차트 & 백테스팅'** 메뉴를\n직접 클릭해서 차트 화면으로 이동해 보세요.",
            style: { top: '130px', left: '260px' }, // 두 번째 메뉴 위치
            arrow: "⬅️ 왼쪽 메뉴 클릭!",
            waitForTab: "dashboard"
        },
        // [2] 차트 화면 설명
        {
            title: "📈 차트 & 백테스팅",
            desc: "잘하셨습니다! 이곳은 실시간 시세와\n자산 그래프를 한눈에 확인하는 곳입니다.",
            style: { top: '50%', left: '50%', transform: 'translate(-50%, -50%)' },
            arrow: null,
            waitForTab: null
        },
        // [3] 슬라이드 챗봇(꿀팁) 설명
        {
            title: "💡 꿀팁: 숨겨진 챗봇!",
            desc: "차트를 보면서 대화하고 싶으신가요?\n**우측의 이 버튼**을 눌러보세요.\n화면을 이동하지 않고도 AI를 호출할 수 있습니다!",
            style: { top: '50%', right: '60px', transform: 'translate(0, -50%)' }, // 우측 토글 버튼 가리킴
            arrow: "➡️ 슬라이드 챗봇 버튼",
            waitForTab: null
        },
        // [4] 보고서 이동 미션
        {
            title: "미션 2: 보고서 메뉴 클릭",
            desc: "이번엔 **'AI 보고서'** 메뉴를 클릭해 볼까요?",
            style: { top: '180px', left: '260px' }, // 세 번째 메뉴 위치
            arrow: "⬅️ 왼쪽 메뉴 클릭!",
            waitForTab: "report"
        },
        // [5] 보고서 설명
        {
            title: "📑 AI 리포트",
            desc: "이곳에서는 AI가 분석한 투자 성과 보고서를\n주기적으로 확인할 수 있습니다.",
            style: { top: '50%', left: '50%', transform: 'translate(-50%, -50%)' },
            arrow: null,
            waitForTab: null
        },
        // [6] 다시 에이전트로 복귀 미션
        {
            title: "미션 3: AI 에이전트로 복귀",
            desc: "이제 본격적인 시작을 위해\n다시 맨 위 **'AI 에이전트'** 탭으로 돌아와 주세요.",
            style: { top: '80px', left: '260px' }, // 첫 번째 메뉴 위치
            arrow: "⬅️ 맨 위 메뉴 클릭!",
            waitForTab: "chat"
        },
        // [7] 종료
        {
            title: "🤖 준비 완료!",
            desc: "이제 아래 입력창을 통해 AI에게\n투자를 명령하거나 조언을 구해보세요!",
            style: { bottom: '100px', left: '50%', transform: 'translate(-50%, 0)' },
            arrow: "⬇️ 여기서 대화 시작",
            waitForTab: null
        }
    ];

    // 탭 변경 감지 및 자동 진행 로직
    useEffect(() => {
        if (!run) return;
        const currentStep = steps[stepIndex];

        // 현재 단계가 '특정 탭을 기다리는 중'이고, 사용자가 그 탭으로 이동했다면?
        if (currentStep.waitForTab && currentTab === currentStep.waitForTab) {
            // 0.5초 뒤에 다음 단계로 넘어감
            setTimeout(() => {
                setStepIndex(prev => prev + 1);
            }, 500);
        }
    }, [currentTab, stepIndex, run]);

    if (!run) return null;

    const currentStep = steps[stepIndex];
    const showNextButton = !currentStep.waitForTab;

    const handleNext = () => {
        if (stepIndex >= steps.length - 1) {
            onFinish();
        } else {
            setStepIndex(prev => prev + 1);
        }
    };

    return (
        <div style={overlayStyle}>
            <div style={boxStyle(currentStep.style)}>
                <h3 style={{ margin: '0 0 10px 0', color: '#4B9CFF', fontSize: '18px' }}>
                    {currentStep.title}
                </h3>
                <p style={{ whiteSpace: 'pre-line', lineHeight: '1.6', color: '#e0e0e0', marginBottom: '20px', fontSize: '14px' }}>
                    {currentStep.desc}
                </p>

                {currentStep.arrow && (
                    <div style={{ color: '#FFD700', fontWeight: 'bold', marginBottom: '15px', fontSize: '16px' }}>
                        {currentStep.arrow}
                    </div>
                )}

                <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
                    <button onClick={onFinish} style={skipBtnStyle}>
                        그만보기
                    </button>
                    {showNextButton && (
                        <button onClick={handleNext} style={nextBtnStyle}>
                            {stepIndex === steps.length - 1 ? "시작하기" : "다음"}
                        </button>
                    )}
                </div>
            </div>
        </div>
    );
}

// --- 스타일 (유지) ---
const overlayStyle = {
    position: 'fixed', inset: 0, backgroundColor: 'rgba(0, 0, 0, 0.3)', zIndex: 99999, pointerEvents: 'none', transition: 'background-color 0.3s'
};

const boxStyle = (pos) => ({
    position: 'absolute', ...pos, width: '320px', backgroundColor: '#1E1E20', border: '1px solid #4B9CFF',
    borderRadius: '12px', padding: '24px', boxShadow: '0 0 25px rgba(75, 156, 255, 0.5)',
    color: 'white', textAlign: 'left', animation: 'fadeIn 0.4s cubic-bezier(0.16, 1, 0.3, 1)',
    transition: 'top 0.4s ease, left 0.4s ease', pointerEvents: 'auto'
});

const nextBtnStyle = {
    padding: '8px 16px', backgroundColor: '#4B9CFF', color: 'white', border: 'none', borderRadius: '6px', cursor: 'pointer', fontWeight: 'bold'
};
const skipBtnStyle = {
    padding: '8px 16px', background: 'transparent', color: '#aaa', border: 'none', cursor: 'pointer', fontSize: '13px'
};