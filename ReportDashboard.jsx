// frontend/src/ReportDashboard.jsx
import React, { useState, useEffect, useRef } from 'react';
import { createChart } from 'lightweight-charts';
import './App.css';

const API_URL = 'http://127.0.0.1:8000';

const ReportContent = ({ text }) => {
    if (!text) return <div className="empty-report">데이터를 분석 중이거나 결과가 없습니다.</div>;
    return (
        <div className="markdown-body">
            {text.split('\n').map((line, i) => (
                <div key={i} style={{ minHeight: '1.2em' }}>
                    {line.startsWith('# ') ? <h1 style={{ color: '#4B9CFF' }}>{line.replace('# ', '')}</h1> :
                        line.startsWith('## ') ? <h2 style={{ color: '#2ebd85', marginTop: '20px' }}>{line.replace('## ', '')}</h2> :
                            line.startsWith('- ') ? <li style={{ marginLeft: '20px' }}>{line.replace('- ', '')}</li> :
                                line}
                </div>
            ))}
        </div>
    );
};

const ReportDashboard = () => {
    // 기본 탭을 'monthly'(전체)로 설정하여 처음부터 전체 데이터를 보여줌
    const [activeTab, setActiveTab] = useState('monthly');
    const [reports, setReports] = useState({ daily: '', weekly: '', monthly: '' });
    const [loading, setLoading] = useState(false);

    const [equityData, setEquityData] = useState([]);
    const [chartData, setChartData] = useState([]);

    const chartContainerRef = useRef(null);
    const chartInstanceRef = useRef(null);
    const areaSeriesRef = useRef(null);
    const toolTipRef = useRef(null);

    // 1. 초기 데이터 로드
    useEffect(() => {
        const fetchBacktestData = async () => {
            try {
                const res = await fetch(`${API_URL}/api/v1/backtest-results`);
                const data = await res.json();
                if (data.equity_curve && data.equity_curve.length > 0) {
                    setEquityData(data.equity_curve);
                }
            } catch (err) {
                console.error("차트 데이터 로드 실패:", err);
            }
        };
        fetchBacktestData();
        if (!reports[activeTab]) fetchReport(activeTab);
    }, [activeTab]);

    // 2. 데이터 가공 (전체 데이터 로직 적용)
    useEffect(() => {
        if (equityData.length === 0) return;

        // (1) 전체 거래 히스토리 추출
        const allTrades = [];
        let lastValue = -1;

        equityData.forEach((item, index) => {
            const isTradeExit = (item.mfe && item.mfe !== 0) || (item.mae && item.mae !== 0);
            const isStartOrEnd = index === 0 || index === equityData.length - 1;

            if (isTradeExit || isStartOrEnd) {
                let time = item.time;
                if (time > 10000000000) time = Math.floor(time / 1000);

                allTrades.push({
                    originalTime: time,
                    value: item.value,
                    pnl: item.value - lastValue,
                    mfe: item.mfe || 0,
                    mae: item.mae || 0
                });
                lastValue = item.value;
            }
        });

        if (allTrades.length > 0) allTrades[0].pnl = 0;

        // (2) 기간 필터링
        let filteredTrades = [];
        const lastItem = allTrades[allTrades.length - 1];

        if (lastItem) {
            const endTime = lastItem.originalTime;
            let startTime = 0;

            if (activeTab === 'daily') {
                startTime = endTime - (24 * 60 * 60);
                filteredTrades = allTrades.filter(t => t.originalTime >= startTime);
            } else if (activeTab === 'weekly') {
                startTime = endTime - (7 * 24 * 60 * 60);
                filteredTrades = allTrades.filter(t => t.originalTime >= startTime);
            } else {
                // [핵심 수정] '월간' 탭은 필터링 없이 '전체 데이터'를 보여줌
                filteredTrades = allTrades;
            }

            // (안전장치) 일간/주간인데 데이터가 너무 없으면 최근 20개 보여줌
            if (activeTab !== 'monthly' && filteredTrades.length < 2) {
                const limit = activeTab === 'daily' ? 20 : 50;
                const startIdx = Math.max(0, allTrades.length - limit);
                filteredTrades = allTrades.slice(startIdx);
            }
        }

        // (3) 차트용 데이터 재구성 (Re-indexing)
        const finalData = filteredTrades.map((item, index) => ({
            time: index, // X축 인덱스
            value: item.value,
            originalTime: item.originalTime,
            pnl: item.pnl,
            mfe: item.mfe,
            mae: item.mae
        }));

        setChartData(finalData);

    }, [activeTab, equityData]);

    // 3. 차트 생성
    useEffect(() => {
        if (!chartContainerRef.current) return;

        if (!chartInstanceRef.current) {
            const chart = createChart(chartContainerRef.current, {
                layout: { background: { type: 'solid', color: '#1a1e23' }, textColor: '#9aa0a6' },
                grid: { vertLines: { color: '#2a2b2e' }, horzLines: { color: '#2a2b2e' } },
                width: chartContainerRef.current.clientWidth,
                height: 300,
                timeScale: {
                    tickMarkFormatter: () => '',
                },
                crosshair: { vertLine: { labelVisible: false } }
            });

            const series = chart.addAreaSeries({
                lineColor: '#2ebd85',
                topColor: 'rgba(46, 189, 133, 0.4)',
                bottomColor: 'rgba(46, 189, 133, 0.0)',
                lineWidth: 2,
            });

            chartInstanceRef.current = chart;
            areaSeriesRef.current = series;

            const resizeObserver = new ResizeObserver(entries => {
                if (entries.length === 0 || !chart) return;
                const { width } = entries[0].contentRect;
                chart.applyOptions({ width });
            });
            resizeObserver.observe(chartContainerRef.current);
        }
    }, []);

    // 4. 데이터 업데이트
    useEffect(() => {
        if (!chartInstanceRef.current || !areaSeriesRef.current || chartData.length === 0) return;

        const chart = chartInstanceRef.current;
        const series = areaSeriesRef.current;

        // X축 라벨 설정
        chart.applyOptions({
            timeScale: {
                tickMarkFormatter: (time) => {
                    const dataPoint = chartData.find(d => d.time === time);
                    if (dataPoint) {
                        const date = new Date(dataPoint.originalTime * 1000);
                        // 일간 탭만 시:분, 나머지는 월/일
                        if (activeTab === 'daily') {
                            const hours = date.getHours().toString().padStart(2, '0');
                            const minutes = date.getMinutes().toString().padStart(2, '0');
                            return `${hours}:${minutes}`;
                        } else {
                            return `${date.getMonth() + 1}/${date.getDate()}`;
                        }
                    }
                    return '';
                }
            }
        });

        series.setData(chartData.map(d => ({ time: d.time, value: d.value })));
        chart.timeScale().fitContent();

    }, [chartData, activeTab]);

    // 5. 툴팁 핸들러
    useEffect(() => {
        if (!chartInstanceRef.current || !areaSeriesRef.current || chartData.length === 0) return;

        const chart = chartInstanceRef.current;
        const series = areaSeriesRef.current;
        const toolTip = toolTipRef.current;

        const handleCrosshairMove = (param) => {
            if (!param.time || param.point.x < 0 || param.point.x > chartContainerRef.current.clientWidth || param.point.y < 0 || param.point.y > chartContainerRef.current.clientHeight) {
                if (toolTip) toolTip.style.display = 'none';
                return;
            }

            const dataPoint = chartData.find(d => d.time === param.time);
            if (!dataPoint) return;

            toolTip.style.display = 'block';
            const dateStr = new Date(dataPoint.originalTime * 1000).toLocaleString();
            const pnlClass = dataPoint.pnl >= 0 ? 'win' : 'loss';

            toolTip.innerHTML = `
                <div class="tooltip-title">📅 ${dateStr}</div>
                <div class="tooltip-row">
                    <span>자산</span>
                    <span class="win" style="color: white">${dataPoint.value.toFixed(2)}</span>
                </div>
                <div class="tooltip-row">
                    <span>손익</span>
                    <span class="${pnlClass}">${dataPoint.pnl > 0 ? '+' : ''}${dataPoint.pnl.toFixed(2)}</span>
                </div>
                <hr style="border-color: #444; margin: 5px 0;">
                <div class="tooltip-row">
                    <span>최대수익</span>
                    <span class="win">+${dataPoint.mfe.toFixed(2)}</span>
                </div>
            `;

            const coordinate = series.priceToCoordinate(dataPoint.value);
            let shiftedX = param.point.x - 60;
            if (shiftedX < 0) shiftedX = 0;
            toolTip.style.left = shiftedX + 'px';
            toolTip.style.top = '10px';
        };

        chart.subscribeCrosshairMove(handleCrosshairMove);
        return () => chart.unsubscribeCrosshairMove(handleCrosshairMove);
    }, [chartData]);

    // --- [신규] 통계 지표 계산 ---
    const calculateStats = () => {
        if (!chartData || chartData.length === 0) return null;

        const totalTrades = chartData.length;
        const winningTrades = chartData.filter(d => d.pnl > 0).length;
        const winRate = totalTrades > 0 ? ((winningTrades / totalTrades) * 100).toFixed(2) : 0;

        // 순손익 (마지막 자산 - 첫 자산)
        const startValue = chartData[0].value - chartData[0].pnl; // 첫 거래 전 자산 추정
        const endValue = chartData[chartData.length - 1].value;
        const totalNetProfit = endValue - startValue;
        const totalNetProfitPercent = startValue > 0 ? ((totalNetProfit / startValue) * 100).toFixed(2) : 0;

        // MDD 계산
        let peak = -Infinity;
        let maxDrawdown = 0;
        let maxDrawdownPercent = 0;

        chartData.forEach(d => {
            if (d.value > peak) peak = d.value;
            const dd = peak - d.value;
            const ddPercent = peak > 0 ? (dd / peak) * 100 : 0;
            if (dd > maxDrawdown) maxDrawdown = dd;
            if (ddPercent > maxDrawdownPercent) maxDrawdownPercent = ddPercent;
        });

        // 수익 지수 (Profit Factor)
        const grossProfit = chartData.reduce((acc, d) => acc + (d.pnl > 0 ? d.pnl : 0), 0);
        const grossLoss = chartData.reduce((acc, d) => acc + (d.pnl < 0 ? Math.abs(d.pnl) : 0), 0);
        const profitFactor = grossLoss > 0 ? (grossProfit / grossLoss).toFixed(3) : '∞';

        return {
            totalNetProfit,
            totalNetProfitPercent,
            maxDrawdown,
            maxDrawdownPercent,
            totalTrades,
            winRate,
            profitFactor
        };
    };

    const stats = calculateStats();

    const fetchReport = async (period) => {
        setLoading(true);
        try {
            const res = await fetch(`${API_URL}/api/v1/generate-report`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ period: period })
            });
            if (!res.ok) throw new Error(`서버 오류 (${res.status})`);
            const data = await res.json();
            setReports(prev => ({ ...prev, [period]: data.report || "⚠️ 보고서 내용이 비어있습니다." }));
        } catch (err) {
            setReports(prev => ({ ...prev, [period]: `❌ 보고서 생성 실패\n\n원인: ${err.message}` }));
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="report-container">
            <div className="report-header">
                <h2 className="report-title">📑 AI 트레이딩 성과 보고서</h2>
                <div className="report-tabs">
                    <button className={`tab-btn ${activeTab === 'daily' ? 'active' : ''}`} onClick={() => setActiveTab('daily')}>일간</button>
                    <button className={`tab-btn ${activeTab === 'weekly' ? 'active' : ''}`} onClick={() => setActiveTab('weekly')}>주간</button>
                    {/* 월간 버튼 클릭 시 전체 데이터를 보여줌 */}
                    <button className={`tab-btn ${activeTab === 'monthly' ? 'active' : ''}`} onClick={() => setActiveTab('monthly')}>전체(월간)</button>
                </div>
            </div>

            <div className="report-controls">
                <button className="generate-btn" onClick={() => fetchReport(activeTab)} disabled={loading}>
                    {loading ? '🔄 분석 중...' : '🔄 보고서 재생성 (AI)'}
                </button>
                <span className="last-updated">
                    {reports[activeTab] && !reports[activeTab].startsWith('❌') ? '✅ AI 분석 완료' : 'ℹ️ 데이터 분석 필요'}
                </span>
            </div>

            {/* [신규] 통계 요약 섹션 (TradingView 스타일) */}
            {stats && (
                <div className="stats-summary-bar" style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    backgroundColor: '#1E1E20',
                    padding: '15px 20px',
                    borderRadius: '8px',
                    marginBottom: '15px',
                    border: '1px solid #333'
                }}>
                    <div className="stat-item">
                        <div style={{ color: '#9aa0a6', fontSize: '12px', marginBottom: '4px' }}>총 손익 (Net Profit)</div>
                        <div style={{ color: stats.totalNetProfit >= 0 ? '#2ebd85' : '#f6465d', fontSize: '18px', fontWeight: 'bold' }}>
                            {stats.totalNetProfit >= 0 ? '+' : ''}{stats.totalNetProfit.toFixed(2)} USDT
                            <span style={{ fontSize: '12px', marginLeft: '5px' }}>({stats.totalNetProfitPercent}%)</span>
                        </div>
                    </div>
                    <div className="stat-item">
                        <div style={{ color: '#9aa0a6', fontSize: '12px', marginBottom: '4px' }}>최대 자본 감소 (MDD)</div>
                        <div style={{ color: '#f6465d', fontSize: '18px', fontWeight: 'bold' }}>
                            {stats.maxDrawdownPercent.toFixed(2)}%
                            <span style={{ fontSize: '12px', marginLeft: '5px', color: '#9aa0a6' }}>(-{stats.maxDrawdown.toFixed(2)})</span>
                        </div>
                    </div>
                    <div className="stat-item">
                        <div style={{ color: '#9aa0a6', fontSize: '12px', marginBottom: '4px' }}>총 거래 횟수</div>
                        <div style={{ color: '#fff', fontSize: '18px', fontWeight: 'bold' }}>
                            {stats.totalTrades}
                        </div>
                    </div>
                    <div className="stat-item">
                        <div style={{ color: '#9aa0a6', fontSize: '12px', marginBottom: '4px' }}>승률 (Win Rate)</div>
                        <div style={{ color: '#fff', fontSize: '18px', fontWeight: 'bold' }}>
                            {stats.winRate}%
                        </div>
                    </div>
                    <div className="stat-item">
                        <div style={{ color: '#9aa0a6', fontSize: '12px', marginBottom: '4px' }}>수익 지수 (Profit Factor)</div>
                        <div style={{ color: '#fff', fontSize: '18px', fontWeight: 'bold' }}>
                            {stats.profitFactor}
                        </div>
                    </div>
                </div>
            )}

            <div className="report-chart-card">
                <div className="card-title-small">
                    📊 {activeTab === 'daily' ? '최근 24시간' : activeTab === 'weekly' ? '최근 7일' : '전체 기간'} 자산 변동 그래프
                </div>
                <div style={{ position: 'relative', width: '100%', height: '100%' }}>
                    <div ref={toolTipRef} className="chart-tooltip"></div>
                    <div ref={chartContainerRef} className="report-chart-wrapper" />
                </div>
            </div>

            <div className="report-paper">
                {loading && !reports[activeTab] ? (
                    <div className="loading-spinner">
                        <div className="spinner"></div>
                        <p>AI가 시장 데이터를 분석하고 있습니다...</p>
                    </div>
                ) : (
                    <ReportContent text={reports[activeTab]} />
                )}
            </div>
        </div>
    );
};

export default ReportDashboard;