// frontend/src/TestCompleteScreen.jsx
import React, { useEffect, useState } from "react";
import "./App.css";

export default function TestCompleteScreen({ onDone }) {
    const [fade, setFade] = useState(false);

    useEffect(() => {
        // 애니메이션 시작
        setTimeout(() => setFade(true), 200);
    }, []);

    return (
        <div className={`test-complete-container ${fade ? "fade-in" : ""}`}>
            <div className="test-complete-box">
                <h1 className="test-complete-title">🎉 테스트 완료!</h1>
                <p className="test-complete-sub">
                    투자 성향 분석이 끝났습니다.<br />
                    지금부터 맞춤 트레이딩 서비스를 시작합니다.
                </p>

                <button className="test-complete-btn" onClick={onDone}>
                    메인 화면으로 이동 →
                </button>
            </div>
        </div>
    );
}
