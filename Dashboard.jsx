// frontend/src/Dashboard.jsx
import React, { useState, useEffect, useRef } from 'react';
import useWebSocket from 'react-use-websocket';
import { createChart } from 'lightweight-charts';
import './App.css';
import './Dashboard.css';
import ChatComponent from './ChatComponent';

const API_URL = 'http://127.0.0.1:8000';
const WS_URL = 'ws://127.0.0.1:8000/ws';

const Dashboard = ({
  backtestMarkers,
  backtestEquity,
  onStrategyChange,
  forceChatOpen,      // [신규] 패널 강제 열기 신호
  triggerGreeting,    // [신규] 인사 시작 신호
  personality,        // [신규] 성향 데이터
  // [신규] 공유 챗봇 상태
  chatMessages,
  setChatMessages,
  chatRecommendations,
  setChatRecommendations,
  chatGreetingDone,
  setChatGreetingDone
}) => {
  // --- 상태 관리 ---
  const [realTimeFills, setRealTimeFills] = useState([]);
  const [currentPriceInfo, setCurrentPriceInfo] = useState({ price: '0.00', change: '0.00', changePercent: '0.00%', high: '0.00', low: '0.00' });
  const [chartData, setChartData] = useState(null);

  const [initialBacktestData, setInitialBacktestData] = useState(null);
  const [fileMarkers, setFileMarkers] = useState([]);
  const [markers, setMarkers] = useState([]);

  // 챗봇 패널 열림 상태
  const [isChatOpen, setIsChatOpen] = useState(false);

  // --- Refs ---
  const chartContainerRef = useRef(null);
  const chartInstanceRef = useRef(null);
  const candleSeriesRef = useRef(null);
  const lastCandleRef = useRef(null);

  const equityContainerRef = useRef(null);
  const equityChartRef = useRef(null);
  const equitySeriesRef = useRef(null);
  const toolTipRef = useRef(null);

  // --- [신규] forceChatOpen 신호가 오면 패널 열기 ---
  useEffect(() => {
    if (forceChatOpen) {
      setIsChatOpen(true);
    }
  }, [forceChatOpen]);

  // --- WebSocket 연결 ---
  const { lastJsonMessage } = useWebSocket(WS_URL, {
    shouldReconnect: () => true,
    reconnectInterval: 3000,
  });

  // 1. 초기 데이터 로드 (API)
  useEffect(() => {
    const fetchData = async () => {
      try {
        const resChart = await fetch(`${API_URL}/api/v1/chart-data`);
        const dataChart = await resChart.json();
        if (!dataChart.error) {
          setChartData(dataChart);
          if (dataChart.candlesticks?.length > 0) {
            const last = dataChart.candlesticks[dataChart.candlesticks.length - 1];
            setCurrentPriceInfo(prev => ({ ...prev, price: last.close.toFixed(2) }));
          }
        }

        const resBacktest = await fetch(`${API_URL}/api/v1/backtest-results`);
        const dataBacktest = await resBacktest.json();
        if (!dataBacktest.error) {
          setInitialBacktestData(dataBacktest.equity_curve);
          if (dataBacktest.markers && dataBacktest.markers.length > 0) {
            setFileMarkers(dataBacktest.markers);
          }
        }

        const resMarkers = await fetch(`${API_URL}/api/v1/chart-markers`);
        const dataMarkers = await resMarkers.json();
        if (Array.isArray(dataMarkers)) setMarkers(dataMarkers);

        const resTrade = await fetch(`${API_URL}/api/v1/trade-history`);
        const dataTrade = await resTrade.json();
        if (!dataTrade.error && dataTrade.trades) {
          const formatted = dataTrade.trades.map(t => ({ side: t.side, fillPx: t.price, sz: t.size, ts: t.time }));
          setRealTimeFills(formatted.slice(0, 20));
        }
      } catch (e) { console.error(e); }
    };
    fetchData();
  }, []);

  // 2. WebSocket 메시지 처리
  useEffect(() => {
    if (!lastJsonMessage) return;
    const { type, data } = lastJsonMessage;

    if (type === 'ticker') {
      const last = parseFloat(data.last);
      const open = parseFloat(data.open24h);
      const percent = open ? ((last - open) / open) * 100 : 0;
      setCurrentPriceInfo({
        price: last.toFixed(2),
        change: (last - open).toFixed(2),
        changePercent: `${percent.toFixed(2)}%`,
        high: parseFloat(data.high24h).toFixed(2),
        low: parseFloat(data.low24h).toFixed(2),
      });
      if (candleSeriesRef.current && lastCandleRef.current) {
        const updated = { ...lastCandleRef.current, close: last, high: Math.max(lastCandleRef.current.high, last), low: Math.min(lastCandleRef.current.low, last) };
        try { candleSeriesRef.current.update(updated); lastCandleRef.current = updated; } catch (e) { }
      }
    } else if (type === 'fill') {
      setRealTimeFills(prev => [data, ...prev.slice(0, 19)]);
    } else if (type === 'marker') {
      setMarkers(prev => [...prev, data]);
    } else if (type === 'new_candle') {
      if (candleSeriesRef.current) {
        try { candleSeriesRef.current.update(data); lastCandleRef.current = data; } catch (e) { }
      }
    }
  }, [lastJsonMessage]);

  // 3. 메인 차트 생성
  useEffect(() => {
    if (!chartContainerRef.current || !chartData) return;
    if (chartInstanceRef.current) {
      try { chartInstanceRef.current.remove(); } catch (e) { }
      chartInstanceRef.current = null;
      candleSeriesRef.current = null;
    }

    const chart = createChart(chartContainerRef.current, {
      layout: { background: { type: 'solid', color: '#151617' }, textColor: '#9aa0a6' },
      grid: { vertLines: { color: '#2a2b2e' }, horzLines: { color: '#2a2b2e' } },
      width: chartContainerRef.current.clientWidth,
      height: chartContainerRef.current.clientHeight,
      timeScale: { timeVisible: true },
    });
    chartInstanceRef.current = chart;

    const series = chart.addCandlestickSeries({ upColor: '#2ebd85', downColor: '#f6465d', borderVisible: false, wickUpColor: '#2ebd85', wickDownColor: '#f6465d' });
    series.setData(chartData.candlesticks);
    candleSeriesRef.current = series;

    if (chartData.candlesticks.length > 0) lastCandleRef.current = chartData.candlesticks[chartData.candlesticks.length - 1];

    const resizeObserver = new ResizeObserver(entries => {
      if (entries.length === 0 || !chart) return;
      const { width, height } = entries[0].contentRect;
      try { chart.applyOptions({ width, height }); } catch (e) { }
    });
    resizeObserver.observe(chartContainerRef.current);

    return () => {
      resizeObserver.disconnect();
      if (chartInstanceRef.current) { try { chartInstanceRef.current.remove(); } catch (e) { } }
      chartInstanceRef.current = null;
      candleSeriesRef.current = null;
    };
  }, [chartData]);

  // 4. 차트 마커 통합
  useEffect(() => {
    const series = candleSeriesRef.current;
    if (!series) return;

    const activeBacktestMarkers = (backtestMarkers && backtestMarkers.length > 0) ? backtestMarkers : fileMarkers;
    const combinedMarkers = [...activeBacktestMarkers, ...markers];

    const formatted = combinedMarkers
      .filter(m => m && typeof m.time !== 'undefined')
      .map(m => {
        let time = m.time;
        if (typeof time === 'number' && time > 10000000000) { time = Math.floor(time / 1000); }
        return { time: time, position: m.position, color: m.color, shape: m.shape, text: m.text || '' };
      })
      .sort((a, b) => a.time - b.time);

    const uniqueMarkers = [];
    const seen = new Set();
    for (let i = formatted.length - 1; i >= 0; i--) {
      const m = formatted[i];
      const key = `${m.time}-${m.text}`;
      if (!seen.has(key)) {
        seen.add(key);
        uniqueMarkers.unshift(m);
      }
    }
    try { series.setMarkers(uniqueMarkers); } catch (e) { }
  }, [markers, backtestMarkers, fileMarkers, chartData]);

  // 5. 백테스트(자산 곡선) 차트 생성
  useEffect(() => {
    const rawData = (backtestEquity && backtestEquity.length > 0) ? backtestEquity : initialBacktestData;
    if (!equityContainerRef.current || !rawData || rawData.length === 0) return;

    if (equityChartRef.current) {
      try { equityChartRef.current.remove(); } catch (e) { }
      equityChartRef.current = null;
    }

    const tradesOnly = [];
    let lastValue = -1;

    try {
      rawData.forEach((item, index) => {
        const isTradeExit = (item.mfe && item.mfe !== 0) || (item.mae && item.mae !== 0);
        const isStartOrEnd = index === 0 || index === rawData.length - 1;

        if (isTradeExit || isStartOrEnd) {
          tradesOnly.push({
            time: index,
            value: item.value,
            originalTime: item.time,
            pnl: item.value - lastValue,
            mfe: item.mfe || 0,
            mae: item.mae || 0
          });
          lastValue = item.value;
        }
      });
      if (tradesOnly.length > 0) tradesOnly[0].pnl = 0;
    } catch (e) { return; }

    const chart = createChart(equityContainerRef.current, {
      layout: { background: { type: 'solid', color: '#151617' }, textColor: '#9aa0a6' },
      grid: { vertLines: { color: '#2a2b2e' }, horzLines: { color: '#2a2b2e' } },
      width: equityContainerRef.current.clientWidth,
      height: equityContainerRef.current.clientHeight,
      timeScale: {
        tickMarkFormatter: (time) => {
          const dataPoint = tradesOnly.find(d => d.time === time);
          if (dataPoint) {
            const date = new Date(dataPoint.originalTime * 1000);
            return `${date.getMonth() + 1}/${date.getDate()}`;
          }
          return '';
        },
      },
      crosshair: { vertLine: { labelVisible: false } }
    });
    equityChartRef.current = chart;

    const series = chart.addAreaSeries({
      lineColor: '#2ebd85',
      topColor: 'rgba(46, 189, 133, 0.4)',
      bottomColor: 'rgba(46, 189, 133, 0.0)',
      lineWidth: 2,
    });

    series.setData(tradesOnly.map(d => ({ time: d.time, value: d.value })));
    equitySeriesRef.current = series;

    const toolTip = toolTipRef.current;

    chart.subscribeCrosshairMove(param => {
      if (!param.time || param.point.x < 0 || param.point.x > equityContainerRef.current.clientWidth || param.point.y < 0 || param.point.y > equityContainerRef.current.clientHeight) {
        if (toolTip) toolTip.style.display = 'none';
        return;
      }

      const dataPoint = tradesOnly.find(d => d.time === param.time);
      if (!dataPoint) return;

      toolTip.style.display = 'block';
      const dateStr = new Date(dataPoint.originalTime * 1000).toLocaleString();
      const pnlClass = dataPoint.pnl >= 0 ? 'win' : 'loss';

      toolTip.innerHTML = `
            <div class="tooltip-title">거래 종료: ${dateStr}</div>
            <div class="tooltip-row">
                <span>현재 자산</span>
                <span class="win" style="color: white">${dataPoint.value.toFixed(2)}</span>
            </div>
            <div class="tooltip-row">
                <span>실현 손익</span>
                <span class="${pnlClass}">${dataPoint.pnl > 0 ? '+' : ''}${dataPoint.pnl.toFixed(2)}</span>
            </div>
            <hr style="border-color: #444; margin: 5px 0;">
            <div class="tooltip-row">
                <span>최대 수익(MFE)</span>
                <span class="win">+${dataPoint.mfe.toFixed(2)}</span>
            </div>
            <div class="tooltip-row">
                <span>최대 손실(MAE)</span>
                <span class="loss">${dataPoint.mae.toFixed(2)}</span>
            </div>
        `;

      const coordinate = series.priceToCoordinate(dataPoint.value);
      let shiftedX = param.point.x - 60;
      if (shiftedX < 0) shiftedX = 0;
      toolTip.style.left = shiftedX + 'px';
      toolTip.style.top = '10px';
    });

    const resizeObserver = new ResizeObserver(entries => {
      if (entries.length === 0 || !chart) return;
      const { width, height } = entries[0].contentRect;
      chart.applyOptions({ width, height });
    });
    resizeObserver.observe(equityContainerRef.current);

    return () => {
      resizeObserver.disconnect();
      if (equityChartRef.current) { equityChartRef.current.remove(); equityChartRef.current = null; }
    };
  }, [initialBacktestData, backtestEquity]);

  const priceColor = parseFloat(currentPriceInfo.change) >= 0 ? '#2ebd85' : '#f6465d';

  return (
    <div className="dashboard-container">

      {/* 메인 컨텐츠 영역 */}
      <div className="dashboard-main-content">

        {/* 헤더 */}
        <div className="header-card">
          <div className="header-content">
            <div className="symbol-group">
              <h2 style={{ margin: 0, color: '#fff', fontSize: '20px' }}>BTC/USDT-3X</h2>
              <span style={{ color: '#9aa0a6', fontSize: '14px' }}>Perpetual</span>
            </div>
            <div className="price-group">
              <span style={{ fontSize: '24px', fontWeight: 'bold', color: priceColor }}>{currentPriceInfo.price}</span>
              <span style={{ color: priceColor }}>{currentPriceInfo.change} ({currentPriceInfo.changePercent})</span>
              <div style={{ display: 'flex', gap: '15px', color: '#9aa0a6', fontSize: '12px' }}>
                <span>High <b style={{ color: '#fff' }}>{currentPriceInfo.high}</b></span>
                <span>Low <b style={{ color: '#fff' }}>{currentPriceInfo.low}</b></span>
              </div>
            </div>
          </div>
        </div>

        {/* 메인 차트 */}
        <div className="main-chart-card">
          <div ref={chartContainerRef} className="chart-wrapper" />
        </div>

        {/* 하단 패널 */}
        <div className="bottom-row">
          <div className="bottom-card">
            <div className="card-title"><span>📈</span> 거래별 성과 (Trade Analysis)</div>
            <div style={{ position: 'relative', flex: 1, minHeight: 0, width: '100%' }}>
              <div ref={toolTipRef} className="chart-tooltip"></div>
              <div ref={equityContainerRef} style={{ width: '100%', height: '100%' }} />
            </div>
          </div>
          <div className="bottom-card">
            <div className="card-title"><span>⚡</span> 실시간 체결</div>
            <div className="fills-header">
              <span className="cell-side">포지션</span>
              <span className="cell-price">가격 (USDT)</span>
              <span className="cell-size">크기 (BTC)</span>
            </div>
            <div className="fills-list">
              {realTimeFills.map((fill, idx) => (
                <div key={idx} className="fill-item">
                  <span className="cell-side" style={{ color: fill.side === 'buy' ? '#2ebd85' : '#f6465d', fontWeight: 'bold' }}>{fill.side ? fill.side.toUpperCase() : 'UNKNOWN'}</span>
                  <span className="cell-price">{fill.fillPx}</span>
                  <span className="cell-size" style={{ color: '#9aa0a6' }}>{fill.sz}</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* 토글 버튼 */}
        <button
          className={`slide-toggle-btn ${isChatOpen ? 'open' : ''}`}
          onClick={() => setIsChatOpen(!isChatOpen)}
          title={isChatOpen ? "챗봇 닫기" : "AI 대화하기"}
        >
          {isChatOpen ? '>' : '<'}
        </button>

      </div>

      {/* 챗봇 슬라이드 패널 */}
      <div className={`slide-chat-panel ${isChatOpen ? 'open' : ''}`}>
        <div className="slide-chat-header">
          <span>🤖 AI Assistant</span>
          <button onClick={() => setIsChatOpen(false)}>✕</button>
        </div>
        <div className="slide-chat-body">
          {/* [수정] ChatComponent에 props 전달 */}
          <ChatComponent
            onStrategyChange={onStrategyChange}
            triggerGreeting={triggerGreeting} // 인사 트리거
            personality={personality}         // 성향 데이터
            // [공유 상태 전달]
            messages={chatMessages}
            setMessages={setChatMessages}
            recommendations={chatRecommendations}
            setRecommendations={setChatRecommendations}
            greetingDone={chatGreetingDone}
            setGreetingDone={setChatGreetingDone}
            isPrimary={false} // 오버레이는 보조 역할
          />
        </div>
      </div>

    </div>
  );
};

export default Dashboard;