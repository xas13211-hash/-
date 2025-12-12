// frontend/src/components/StrategyModal.jsx
import { useState, useEffect, useRef } from "react";
import { createChart } from "lightweight-charts";
import "./StrategyUI.css";

const API_BASE = "http://localhost:8000";

function StrategyModal({ strategyId, onClose }) {
  const [detail, setDetail] = useState(null);
  const [loading, setLoading] = useState(true);

  const chartRef = useRef(null);
  const chartInstance = useRef(null);

  async function fetchStrategyDetail() {
    try {
      const res = await fetch(`${API_BASE}/api/v1/strategy/detail/${strategyId}`);
      const data = await res.json();
      setDetail(data);
    } catch (e) {
      console.error("전략 상세 오류:", e);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    fetchStrategyDetail();
  }, [strategyId]);

  // 차트 렌더링
  useEffect(() => {
    // [핵심 변경] equity_curve(전체) 대신 equity_over_trades(거래별) 사용
    const tradeData = detail?.backtest?.equity_over_trades;

    if (!tradeData || tradeData.length === 0 || !chartRef.current) return;

    if (chartInstance.current) {
      chartInstance.current.remove();
    }

    const chart = createChart(chartRef.current, {
      width: chartRef.current.clientWidth,
      height: 250,
      layout: {
        background: { type: 'solid', color: '#1E1E20' },
        textColor: '#D1D5DB',
      },
      grid: {
        vertLines: { color: '#374151' },
        horzLines: { color: '#374151' },
      },
      timeScale: {
        timeVisible: true,
        secondsVisible: false,
        // X축을 'No.1, No.2' 거래 순번으로 표시
        tickMarkFormatter: (time) => `No.${time}`
      },
      localization: {
        priceFormatter: p => p.toFixed(2),
      },
      crosshair: {
        vertLine: {
          labelVisible: false, // 세로선 라벨 숨김 (깔끔하게)
        }
      }
    });

    const series = chart.addAreaSeries({
      lineColor: '#2ebd85',
      topColor: 'rgba(46, 189, 133, 0.4)',
      bottomColor: 'rgba(46, 189, 133, 0.0)',
      lineWidth: 2,
    });

    // [핵심] 데이터 매핑: 순수하게 거래 횟수(Index) 기준으로 차트 생성
    const chartData = tradeData.map((p, index) => ({
      time: index + 1,        // 1, 2, 3... (거래 순서)
      value: p.value,         // 자산 가치
      // custom field (툴팁용 정보가 필요하면 백엔드에서 더 보내야 함)
    }));

    series.setData(chartData);
    chart.timeScale().fitContent();

    chartInstance.current = chart;

    const handleResize = () => {
      if (chartRef.current && chart) {
        chart.applyOptions({ width: chartRef.current.clientWidth });
      }
    };
    window.addEventListener('resize', handleResize);

    return () => window.removeEventListener('resize', handleResize);

  }, [detail]);

  if (loading || !detail) {
    return (
      <div className="modal-backdrop">
        <div className="modal" style={{ color: 'white' }}>데이터 불러오는 중...</div>
      </div>
    );
  }

  // 상단 표시 데이터 보정 (DB 데이터 우선)
  const displayROI = detail.optimizer?.expected_return || detail.backtest.roi;
  // 거래 횟수가 0이면 백엔드에서 trade_count를 제대로 못 가져온 것이므로, 
  // equity_over_trades 배열 길이로 대체해서 보여줌
  const displayCount = detail.backtest.trade_count > 0
    ? detail.backtest.trade_count
    : (detail.backtest.equity_over_trades?.length || 0);

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>{detail.name}</h2>
          <span className={`risk-pill ${detail.risk_level}`}>
            {detail.risk_level}
          </span>
          <button className="close-btn" onClick={onClose}>×</button>
        </div>

        <p className="strategy-full-desc">{detail.description}</p>

        <h3 className="section-title">📊 백테스트 결과 (최적화 적용)</h3>
        <div className="metric-grid">
          <div><span>ROI</span><strong className={displayROI >= 0 ? "positive" : "negative"}>{displayROI}%</strong></div>
          <div><span>MDD</span><strong className="negative">{detail.backtest?.mdd}%</strong></div>
          <div><span>최종 자산</span><strong>{detail.backtest?.final_equity.toLocaleString()} USDT</strong></div>
          <div><span>거래 수</span><strong>{displayCount}회</strong></div>
        </div>

        <div className="chart-box" ref={chartRef}></div>

        <h3 className="section-title">⚙ 추천 설정 (AI Optimized)</h3>
        <div className="metric-grid">
          <div><span>레버리지</span><strong>x{detail.optimizer?.best_leverage}</strong></div>
          <div><span>비중</span><strong>{detail.optimizer?.best_risk_percent}%</strong></div>
          <div><span>예상 수익</span><strong className="positive">{detail.optimizer?.expected_return}%</strong></div>
          <div><span>예상 MDD</span><strong className="negative">{detail.optimizer?.expected_mdd}%</strong></div>
        </div>

        <button className="select-btn" onClick={() => alert("전략 적용 완료! (실제 매매가 시작됩니다)")}>
          이 전략으로 자동매매 시작하기
        </button>
      </div>
    </div>
  );
}

export default StrategyModal;