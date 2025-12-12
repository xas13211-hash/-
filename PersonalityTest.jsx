// frontend/src/components/PersonalityTest.jsx
import React, { useState, useEffect } from "react";
import "../App.css"; // 상위 폴더의 CSS 파일 참조

// 백엔드 주소 (설정에 따라 다를 수 있음)
const API_URL = "http://127.0.0.1:8000";

export default function PersonalityTest({ onFinish }) {
    const [currentQuestion, setCurrentQuestion] = useState(null);
    const [history, setHistory] = useState([]); // { question, answer } 기록 저장
    const [totalScore, setTotalScore] = useState(0);
    const [loading, setLoading] = useState(true);

    // 질문 횟수 (AI 면접을 몇 번 할지 설정)
    const MAX_QUESTIONS = 10;

    // --- [핵심] AI에게 다음 질문 요청하는 함수 ---
    const fetchNextQuestion = async (currentHistory) => {
        setLoading(true);
        try {
            const res = await fetch(`${API_URL}/api/v1/personality/next-question`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ history: currentHistory })
            });
            const data = await res.json();
            setCurrentQuestion(data);
        } catch (err) {
            console.error(err);
            alert("AI 면접관을 연결하는데 실패했습니다.");
        } finally {
            setLoading(false);
        }
    };

    // 컴포넌트 처음 뜰 때 첫 질문 요청
    useEffect(() => {
        fetchNextQuestion([]);
    }, []);

    // --- 답변 선택 시 처리 ---
    const handleSelectOption = (optionText, score) => {
        const newScore = totalScore + score;

        // 내 답변을 기록에 추가
        const newHistory = [
            ...history,
            { question: currentQuestion.q, answer: optionText }
        ];

        setTotalScore(newScore);
        setHistory(newHistory);

        // 목표 질문 수에 도달했는지 확인
        if (newHistory.length >= MAX_QUESTIONS) {
            // 끝났으면 결과 전송 (App.jsx로 점수 전달)
            onFinish({ score: newScore });
        } else {
            // 아직 남았으면 AI에게 이 기록을 주고 다음 질문을 받아옴
            fetchNextQuestion(newHistory);
        }
    };

    return (
        <div className="intro-container">
            <div className="intro-box" style={{ maxWidth: '600px' }}>
                <h2 className="test-title">
                    🤖 AI 투자 성향 심층 면접 ({history.length + 1}/{MAX_QUESTIONS})
                </h2>

                {loading ? (
                    <div className="loading-spinner">
                        <div className="spinner"></div>
                        <p style={{ marginTop: '20px', color: '#aaa' }}>
                            AI가 당신의 답변을 분석하고<br />다음 질문을 생각 중입니다...
                        </p>
                    </div>
                ) : (
                    <>
                        <p className="test-question" style={{ whiteSpace: 'pre-line', lineHeight: '1.5' }}>
                            {currentQuestion?.q}
                        </p>

                        <div className="test-options">
                            {currentQuestion?.options?.map((o, i) => (
                                <button
                                    key={i}
                                    className="test-option-btn"
                                    onClick={() => handleSelectOption(o.t, o.s)}
                                >
                                    {o.t}
                                </button>
                            ))}
                        </div>
                    </>
                )}
            </div>
        </div>
    );
}