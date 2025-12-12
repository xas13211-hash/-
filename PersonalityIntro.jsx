// components/PersonalityIntro.jsx
import React from "react";
import "../App.css";

export default function PersonalityIntro({ onStart }) {
    return (
        <div className="intro-container">
            <div className="intro-box">
                <h1>📊 투자 성향 분석</h1>
                <p>
                    AI 트레이딩 에이전트는 투자자의 성향에 맞는
                    가장 적절한 매매 전략을 추천합니다.<br /><br />
                    아래 테스트는 약 30초 정도 소요됩니다.
                </p>

                <button className="intro-btn" onClick={onStart}>
                    테스트 시작하기
                </button>
            </div>
        </div>
    );
}
