import React, { useState, useEffect } from "react";
import "./App.css";

// 화면 컴포넌트들
import IntroScreen from "./IntroScreen";
import PersonalityIntro from "./components/PersonalityIntro";
import PersonalityTest from "./components/PersonalityTest";
import TestCompleteScreen from "./TestCompleteScreen";

// 메인 기능 컴포넌트들
import ChatComponent from "./ChatComponent";
import Dashboard from "./Dashboard";
import ReportDashboard from "./ReportDashboard";

// 튜토리얼 컴포넌트
import AppTutorial from "./components/AppTutorial";

function App() {
    // 1) 상태 초기화
    const [step, setStep] = useState("loading");
    const [personalityData, setPersonalityData] = useState(null);

    // 2) 튜토리얼 & 챗봇 제어 상태
    const [runTutorial, setRunTutorial] = useState(false);
    const [triggerGreeting, setTriggerGreeting] = useState(false);
    const [forceChatOpen, setForceChatOpen] = useState(false);

    // 3) 메인 앱 UI 상태
    // [설정] 앱 첫 진입 시 '챗봇' 화면과 '펼쳐진 사이드바'로 시작
    const [activeTab, setActiveTab] = useState("chat");
    const [sidebarOpen, setSidebarOpen] = useState(true);

    // 4) 백테스트 데이터 공유 상태
    const [backtestMarkers, setBacktestMarkers] = useState([]);
    const [backtestEquity, setBacktestEquity] = useState([]);

    // 5) [신규] 챗봇 상태 공유 (메인 탭 <-> 대시보드 오버레이 동기화)
    const [chatMessages, setChatMessages] = useState([]);
    const [chatRecommendations, setChatRecommendations] = useState([]);
    const [chatGreetingDone, setChatGreetingDone] = useState(false);

    // --- 앱 켜질 때 "기존 사용자"인지 확인 (로컬스토리지 + 서버 확인) ---
    useEffect(() => {
        const checkPersistence = async () => {
            const savedScore = localStorage.getItem("userScore");
            const isDone = localStorage.getItem("isTestDone");

            if (isDone && savedScore) {
                // 1. 로컬스토리지에 있으면 바로 사용
                setPersonalityData({ score: parseInt(savedScore, 10) });
                setStep("app");
                // 저장된 상태에서도 챗봇 인사가 나오도록 트리거
                setTimeout(() => setTriggerGreeting(true), 1000);
            } else {
                // 2. 로컬스토리지에 없으면 서버에 저장된 성향이 있는지 확인
                try {
                    // [Fix] 서버 응답이 늦거나 없을 때 무한 로딩 방지 (3초 타임아웃)
                    const controller = new AbortController();
                    const timeoutId = setTimeout(() => controller.abort(), 3000);

                    const res = await fetch('http://127.0.0.1:8000/api/v1/personality', {
                        signal: controller.signal
                    });
                    clearTimeout(timeoutId);

                    const data = await res.json();
                    if (data.score && data.score > 0) {
                        // 서버에 데이터가 있으면 복구
                        setPersonalityData({ score: data.score });
                        localStorage.setItem("userScore", data.score);
                        localStorage.setItem("isTestDone", "true");
                        setStep("app");
                        // 튜토리얼은 이미 본 것으로 간주하거나, 필요하면 true로 설정
                        // 여기서는 바로 챗봇 인사를 유도하기 위해 튜토리얼 없이 인사 트리거만
                        setTimeout(() => setTriggerGreeting(true), 1000);
                    } else {
                        // 서버에도 없으면 인트로 시작
                        setStep("intro");
                    }
                } catch (err) {
                    console.error("성향 확인 실패 (또는 타임아웃):", err);
                    setStep("intro");
                }
            }
        };
        checkPersistence();
    }, []);

    // 전략 변경 시 차트 데이터 업데이트
    const handleStrategyUpdate = (data) => {
        if (data.markers) setBacktestMarkers([...data.markers]);
        if (data.equity_curve) setBacktestEquity([...data.equity_curve]);
    };

    // 테스트 완료 후 메인 앱 진입 핸들러
    const handleEnterApp = () => {
        localStorage.setItem("isTestDone", "true");
        if (personalityData) {
            localStorage.setItem("userScore", personalityData.score);
        }

        setStep("app");

        // 화면이 다 그려질 시간을 0.5초 준 뒤에 튜토리얼 시작
        setTimeout(() => {
            setRunTutorial(true);
        }, 500);
    };

    // 튜토리얼 완료 핸들러
    const handleTutorialFinish = () => {
        setRunTutorial(false);

        // 튜토리얼 종료 후 챗봇 탭으로 이동하여 인사 듣기
        setActiveTab("chat");

        // 0.5초 뒤 AI 인사 시작
        setTimeout(() => setTriggerGreeting(true), 500);
    };

    // --- 화면 렌더링 분기 ---

    // 0. 로딩 중
    if (step === "loading") return <div className="app-container" style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', color: 'white' }}>Loading...</div>;

    // 1. 인트로/테스트 단계
    if (step === "intro") return <IntroScreen onStart={() => setStep("p_intro")} />;
    if (step === "p_intro") return <PersonalityIntro onStart={() => setStep("test")} />;
    if (step === "test") return <PersonalityTest onFinish={(result) => { setPersonalityData(result); setStep("complete"); }} />;
    if (step === "complete") return <TestCompleteScreen onDone={handleEnterApp} />;

    // 2. 메인 앱 (step === "app")
    return (
        <div className="app-container">
            {/* 튜토리얼 컴포넌트 */}
            <AppTutorial
                run={runTutorial}
                onFinish={handleTutorialFinish}
                currentTab={activeTab} // [핵심] 현재 보고 있는 탭 정보를 튜토리얼에 전달
            />

            <aside className={`sidebar ${sidebarOpen ? "open" : "closed"}`}>
                <div className="sidebar-top">
                    <button className="menu-toggle-btn" onClick={() => setSidebarOpen(!sidebarOpen)}>
                        <span className="icon">☰</span>
                    </button>
                    {sidebarOpen && <span className="app-logo-text">Trader</span>}
                </div>
                <nav className="sidebar-menu">
                    <button className={`menu-item ${activeTab === "chat" ? "active" : ""}`} onClick={() => setActiveTab("chat")}>
                        <span className="icon">💬</span>{sidebarOpen && <span className="label">AI 에이전트</span>}
                    </button>
                    <button className={`menu-item ${activeTab === "dashboard" ? "active" : ""}`} onClick={() => setActiveTab("dashboard")}>
                        <span className="icon">📈</span>{sidebarOpen && <span className="label">차트 & 백테스팅</span>}
                    </button>
                    <button className={`menu-item ${activeTab === "report" ? "active" : ""}`} onClick={() => setActiveTab("report")}>
                        <span className="icon">📑</span>{sidebarOpen && <span className="label">AI 보고서</span>}
                    </button>
                </nav>
            </aside>

            <main className="main-content-area">
                {/* 1) 챗봇 탭 */}
                <div style={{ display: activeTab === "chat" ? "block" : "none", height: "100%", width: "100%" }}>
                    <ChatComponent
                        personality={personalityData}
                        onStrategyChange={handleStrategyUpdate}
                        triggerGreeting={triggerGreeting}
                        // [공유 상태 전달]
                        messages={chatMessages}
                        setMessages={setChatMessages}
                        recommendations={chatRecommendations}
                        setRecommendations={setChatRecommendations}
                        greetingDone={chatGreetingDone}
                        setGreetingDone={setChatGreetingDone}
                        isPrimary={true} // 메인 탭이므로 초기화 담당
                    />
                </div>

                {/* 2) 대시보드 탭 */}
                <div style={{ display: activeTab === "dashboard" ? "block" : "none", height: "100%", width: "100%", overflowY: "auto" }}>
                    <Dashboard
                        backtestMarkers={backtestMarkers}
                        backtestEquity={backtestEquity}
                        onStrategyChange={handleStrategyUpdate}
                        forceChatOpen={forceChatOpen}
                        triggerGreeting={triggerGreeting}
                        personality={personalityData}
                        // [공유 상태 전달]
                        chatMessages={chatMessages}
                        setChatMessages={setChatMessages}
                        chatRecommendations={chatRecommendations}
                        setChatRecommendations={setChatRecommendations}
                        chatGreetingDone={chatGreetingDone}
                        setChatGreetingDone={setChatGreetingDone}
                    />
                </div>

                {/* 3) 보고서 탭 */}
                <div style={{ display: activeTab === "report" ? "block" : "none", height: "100%", width: "100%" }}>
                    <ReportDashboard />
                </div>
            </main>
        </div>
    );
}

export default App;