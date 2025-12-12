// frontend/src/IntroScreen.jsx
import React, { useEffect, useState } from "react";
import "./IntroScreen.css";

export default function IntroScreen({ onStart }) {
    const [fadeOut, setFadeOut] = useState(false);

    const handleStart = () => {
        setFadeOut(true);

        // 페이드아웃 600ms 후 메인 화면으로 전환
        setTimeout(() => {
            onStart();
        }, 600);
    };

    return (
        <div className={`intro-container ${fadeOut ? "fade-out" : ""}`}>
            <div className="intro-box">

                {/* 로고 애니메이션 */}
                <div className="intro-robot bounce">🤖</div>

                <h1 className="intro-title">AI 트레이딩 에이전트</h1>

                <p className="intro-text">
                    자동매매 · 분석 · 전략설계까지<br />
                    당신의 투자 파트너를 소개합니다.
                </p>

                <button className="intro-btn" onClick={handleStart}>
                    시작하기
                </button>
            </div>
        </div>
    );
}
