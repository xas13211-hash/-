import React, { useState, useEffect, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import StrategyModal from './components/StrategyModal';
import './App.css';

// personality: 성향 점수 객체
// onStrategyChange: 전략 변경 시 부모(App/Dashboard)에게 알림
// triggerGreeting: 튜토리얼 종료 후 인사 시작 신호
// [신규] messages, setMessages 등: 부모(App.jsx)에서 관리하는 공유 상태
// [신규] isPrimary: 메인 탭(true)인지 오버레이(false)인지 구분 (데이터 로딩 책임)
const ChatComponent = ({
  personality,
  onStrategyChange,
  triggerGreeting,
  messages,
  setMessages,
  recommendations,
  setRecommendations,
  greetingDone,
  setGreetingDone,
  isPrimary
}) => {

  const [input, setInput] = useState('');

  // 전략 상세 모달 상태 (로컬 관리)
  const [selectedStrategyId, setSelectedStrategyId] = useState(null);

  const messagesEndRef = useRef(null);

  // 스크롤 자동 이동
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => { scrollToBottom(); }, [messages, recommendations]);

  // 1. 기존 대화 내역 불러오기 (Primary 인스턴스만 수행)
  useEffect(() => {
    if (!isPrimary) return; // 오버레이는 로딩하지 않음 (공유 상태 사용)

    const fetchHistory = async () => {
      try {
        const res = await fetch('http://127.0.0.1:8000/api/v1/chat/history');
        const data = await res.json();
        if (Array.isArray(data) && data.length > 0) {
          setMessages(data);
          // 기록이 있으면 이미 인사를 나눈 것으로 간주
          setGreetingDone(true);
        }
      } catch (err) {
        console.error("대화 내역 로드 실패:", err);
      }
    };
    fetchHistory();
  }, [isPrimary, setMessages, setGreetingDone]);

  // 2. [핵심] 튜토리얼 종료 후 AI가 먼저 말걸기 (+ 카드 목록 띄우기)
  useEffect(() => {
    if (!isPrimary) return; // 오버레이는 인사 트리거 무시

    const sayHello = async () => {
      // 신호가 왔고(trigger), 아직 인사 안 했고(!done), 성향 데이터가 있을 때
      if (triggerGreeting && !greetingDone && personality) {
        setGreetingDone(true);

        // 로딩 표시
        setMessages(prev => [...prev, { sender: 'bot', text: 'Thinking...' }]);

        try {
          // 성향 점수를 보내서 인사말과 추천 목록을 받아옴
          const res = await fetch('http://127.0.0.1:8000/api/v1/chat/greeting', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ score: personality.score || 0 })
          });
          const data = await res.json();

          // 1) 텍스트 메시지 업데이트 (Thinking -> 실제 답변)
          setMessages(prev => {
            const newMsgs = [...prev];
            newMsgs.pop();
            return [...newMsgs, { sender: 'bot', text: data.reply }];
          });

          // 2) [수정됨] 백엔드에서 보낸 'recommendations' 데이터가 있으면 화면에 띄움
          if (data.recommendations && data.recommendations.length > 0) {
            setRecommendations(data.recommendations);
          } else {
            setRecommendations([]);
          }

        } catch (err) {
          console.error(err);
          // 에러 발생 시 로딩 메시지 제거
          setMessages(prev => {
            const newMsgs = [...prev];
            newMsgs.pop();
            return newMsgs;
          });
        }
      }
    };
    sayHello();
  }, [triggerGreeting, personality, greetingDone, isPrimary, setGreetingDone, setMessages, setRecommendations]);


  // --- 사용자 메시지 전송 ---
  const sendMessage = async () => {
    if (!input.trim()) return;

    const userMsg = { sender: 'user', text: input };
    setMessages(prev => [...prev, userMsg]);
    setInput('');

    try {
      const res = await fetch('http://127.0.0.1:8000/api/v1/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: input,
          // 대화 중에도 성향 점수를 참고할 수 있도록 전달 (선택사항)
          personality: personality?.score
        })
      });

      const data = await res.json();
      setMessages(prev => [...prev, { sender: 'bot', text: data.reply }]);

      // 일반 대화 중에도 추천 목록이 오면 갱신
      if (data.recommendations && data.recommendations.length > 0) {
        setRecommendations(data.recommendations);
      } else {
        // 추천이 없으면 목록을 비우지 않고 유지하거나, 필요에 따라 []로 초기화
        // 여기서는 대화 흐름상 유지하는 게 자연스러울 수 있음
        // setRecommendations([]); 
      }

    } catch (err) {
      console.error(err);
      setMessages(prev => [...prev, { sender: 'bot', text: '🔴 서버 연결 실패.' }]);
    }
  };

  // --- 전략 선택 로직 ---
  const selectStrategy = async (id, name) => {
    if (confirm(`'${name}' 전략으로 변경하고 자동매매를 진행하시겠습니까?`)) {
      try {
        const res = await fetch('http://127.0.0.1:8000/api/v1/select-strategy', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ strategy_id: id })
        });
        const data = await res.json();
        alert(data.message);

        // 부모 컴포넌트(App/Dashboard)에 차트 업데이트 알림
        if (onStrategyChange) {
          onStrategyChange({
            markers: data.markers,
            equity_curve: data.equity_curve
          });
        }

        setRecommendations([]); // 선택했으니 추천 리스트는 닫기

        const sysMsg = {
          sender: 'bot',
          text: `✅ **전략이 '${name}'(으)로 설정되었습니다.**\n\n이제 **[차트 & 백테스팅]** 탭으로 이동하시면 자동매매 진행 상황을 실시간으로 확인하실 수 있습니다.\n\n또한 **[AI 보고서]** 탭에서는 리스크 관리 현황과 추세 변화에 따른 전략 변경 제안을 확인하실 수 있습니다.`
        };
        setMessages(prev => [...prev, sysMsg]);

      } catch (err) {
        alert("전략 변경 실패");
      }
    }
  };

  return (
    <div className="full-chat-container">
      <div className="chat-messages-area">
        {messages.map((msg, idx) => (
          <div key={idx} style={{
            alignSelf: msg.sender === 'user' ? 'flex-end' : 'flex-start',
            backgroundColor: msg.sender === 'user' ? '#4B9CFF' : '#2a2b2e',
            padding: '12px 16px',
            borderRadius: '12px',
            maxWidth: '70%',
            color: 'white',
            marginBottom: '10px',
            boxShadow: '0 2px 5px rgba(0,0,0,0.1)',
            lineHeight: '1.6',
            wordBreak: 'break-word',
            borderTopRightRadius: msg.sender === 'user' ? '2px' : '12px',
            borderTopLeftRadius: msg.sender === 'bot' ? '2px' : '12px',
          }}>
            {msg.sender === 'bot'
              ? <div className="markdown-content"><ReactMarkdown>{msg.text}</ReactMarkdown></div>
              : msg.text
            }
          </div>
        ))}
        <div ref={messagesEndRef} />

        {/* AI 추천 전략 리스트 카드 영역 */}
        {recommendations.length > 0 && (
          <div className="strategy-list" style={{ width: '80%', alignSelf: 'flex-start', marginBottom: '20px', marginTop: '10px' }}>
            <div style={{ color: '#aaa', fontSize: '12px', marginBottom: '8px', marginLeft: '5px' }}>▼ 추천 전략 목록</div>
            {recommendations.map(strat => (
              <div key={strat.id} className="strategy-card" style={{ backgroundColor: '#1E1E20', border: '1px solid #444', padding: '15px', borderRadius: '10px', marginBottom: '10px' }}>
                <div className="card-header" style={{ color: '#4B9CFF', fontWeight: 'bold', marginBottom: '5px', fontSize: '15px' }}>
                  {strat.name}
                </div>
                <div className="card-stats" style={{ fontSize: '13px', color: '#ccc', marginBottom: '10px' }}>
                  예상 수익(ROI): <span className="win" style={{ color: '#2ebd85', fontWeight: 'bold' }}>{strat.return}%</span> |
                  MDD: <span className="loss" style={{ color: '#f6465d', fontWeight: 'bold' }}>{strat.mdd}%</span>
                </div>
                <div style={{ display: 'flex', gap: '8px' }}>
                  <button
                    onClick={() => selectStrategy(strat.id, strat.name)}
                    style={{ flex: 1, padding: '10px', backgroundColor: '#333', border: 'none', color: 'white', borderRadius: '6px', cursor: 'pointer', fontWeight: 'bold' }}
                  >
                    선택하기
                  </button>
                  <button
                    onClick={() => setSelectedStrategyId(strat.id)}
                    style={{ flex: 1, padding: '10px', backgroundColor: '#4B9CFF', border: 'none', color: 'white', borderRadius: '6px', cursor: 'pointer', fontWeight: 'bold' }}
                  >
                    상세보기
                  </button>
                </div>
              </div>
            ))}

            <div style={{ marginTop: '15px', padding: '10px', backgroundColor: 'rgba(75, 156, 255, 0.1)', borderRadius: '8px', fontSize: '13px', color: '#ddd', lineHeight: '1.5' }}>
              ℹ️ <strong>안내</strong><br />
              전략 선택 시 <strong>자동매매</strong>를 실시하게 되며,<br />
              차트 목록에서 <strong>매수/매도 기록</strong>을 확인할 수 있습니다.
            </div>
          </div>
        )}
      </div>

      <div className="chat-input-wrapper">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyPress={(e) => e.key === 'Enter' && sendMessage()}
          placeholder="AI에게 명령을 입력하세요..." />
        <button onClick={sendMessage}>➤</button>
      </div>

      {/* 전략 상세 모달 */}
      {selectedStrategyId && (
        <StrategyModal
          strategyId={selectedStrategyId}
          onClose={() => setSelectedStrategyId(null)}
        />
      )}
    </div>
  );
};

export default ChatComponent;