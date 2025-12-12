// frontend/src/components/ReActDashboard.jsx
import React, { useState, useEffect } from 'react';

const ReActDashboard = () => {
    const [status, setStatus] = useState(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);

    const fetchStatus = async () => {
        try {
            const res = await fetch('http://localhost:8000/api/v1/react/status');
            const data = await res.json();
            setStatus(data);
        } catch (err) {
            console.error("Failed to fetch ReAct status:", err);
        }
    };

    const handleAnalyze = async () => {
        setLoading(true);
        setError(null);
        try {
            const res = await fetch('http://localhost:8000/api/v1/react/analyze', {
                method: 'POST',
            });
            const data = await res.json();
            if (data.status === 'success') {
                await fetchStatus(); // Refresh status
            } else {
                setError(data.message);
            }
        } catch (err) {
            setError(err.message);
        } finally {
            setLoading(false);
        }
    };

    const handleApproveSwitch = async () => {
        if (!confirm("Are you sure you want to switch the strategy?")) return;

        setLoading(true);
        try {
            const res = await fetch('http://localhost:8000/api/v1/react/approve-switch', {
                method: 'POST',
            });
            const data = await res.json();
            if (data.status === 'success') {
                alert(data.message);
                await fetchStatus();
            } else {
                alert("Error: " + data.message);
            }
        } catch (err) {
            alert("Error: " + err.message);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchStatus();
        const interval = setInterval(fetchStatus, 5000); // Poll every 5 seconds
        return () => clearInterval(interval);
    }, []);

    if (!status) return <div className="p-4 text-gray-400">Loading AI Agent status...</div>;

    return (
        <div className="bg-gray-900 text-white p-6 rounded-lg shadow-lg border border-gray-800 mt-6">
            <div className="flex justify-between items-center mb-6">
                <div>
                    <h2 className="text-2xl font-bold bg-gradient-to-r from-blue-400 to-purple-500 bg-clip-text text-transparent">
                        🤖 AI Market Analysis (ReAct Agent)
                    </h2>
                    <p className="text-gray-400 text-sm mt-1">
                        Autonomous market analysis and strategy selection engine
                    </p>
                </div>
            </div>

            {error && (
                <div className="bg-red-900/50 border border-red-500 text-red-200 p-3 rounded mb-4">
                    ⚠️ {error}
                </div>
            )}

            {/* ReAct Cycle Display */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
                <div className="bg-gray-800/50 p-4 rounded-lg border border-gray-700">
                    <h3 className="text-blue-400 font-semibold mb-2 flex items-center">
                        <span className="mr-2">👁️</span> Observation
                    </h3>
                    <p className="text-sm text-gray-300 whitespace-pre-line min-h-[80px]">
                        {status.observation || "Waiting for data..."}
                    </p>
                </div>

                <div className="bg-gray-800/50 p-4 rounded-lg border border-gray-700">
                    <h3 className="text-purple-400 font-semibold mb-2 flex items-center">
                        <span className="mr-2">💭</span> Thought
                    </h3>
                    <p className="text-sm text-gray-300 whitespace-pre-line min-h-[80px]">
                        {status.thought || "Processing..."}
                    </p>
                </div>

                <div className="bg-gray-800/50 p-4 rounded-lg border border-gray-700 relative">
                    <h3 className="text-green-400 font-semibold mb-2 flex items-center">
                        <span className="mr-2">⚡</span> Action
                    </h3>
                    <p className="text-sm text-gray-300 whitespace-pre-line min-h-[80px]">
                        {status.action || "Idle"}
                    </p>

                    {status.action && status.action.includes("SWITCH") && (
                        <button
                            onClick={handleApproveSwitch}
                            className="absolute bottom-4 right-4 bg-green-600 hover:bg-green-500 text-xs px-3 py-1 rounded shadow animate-pulse"
                        >
                            ✅ Approve Switch
                        </button>
                    )}
                </div>
            </div>

            {/* Strategy Ranking Table */}
            {status.analysis_results && status.analysis_results.length > 0 && (
                <div className="overflow-x-auto">
                    <h3 className="text-xl font-semibold mb-4 text-gray-200">🏆 Strategy Rankings</h3>
                    <table className="w-full text-left border-collapse">
                        <thead>
                            <tr className="text-gray-400 border-b border-gray-700 text-sm">
                                <th className="p-3">Rank</th>
                                <th className="p-3">Strategy Name</th>
                                <th className="p-3">ROI (2 Weeks)</th>
                                <th className="p-3">MDD</th>
                                <th className="p-3">Trades</th>
                                <th className="p-3">Risk Level</th>
                            </tr>
                        </thead>
                        <tbody className="text-sm">
                            {status.analysis_results.slice(0, 5).map((strat, index) => (
                                <tr
                                    key={strat.id}
                                    className={`border-b border-gray-800 hover:bg-gray-800/30 transition-colors ${index === 0 ? 'bg-yellow-900/10' : ''
                                        }`}
                                >
                                    <td className="p-3">
                                        {index === 0 ? '🥇' : index === 1 ? '🥈' : index === 2 ? '🥉' : index + 1}
                                    </td>
                                    <td className="p-3 font-medium text-blue-300">{strat.name}</td>
                                    <td className={`p-3 font-bold ${strat.roi >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                        {strat.roi}%
                                    </td>
                                    <td className="p-3 text-red-300">{strat.mdd}%</td>
                                    <td className="p-3 text-gray-400">{strat.trade_count}</td>
                                    <td className="p-3">
                                        <span className={`px-2 py-1 rounded text-xs ${strat.risk_level === 'Aggressive' ? 'bg-red-900/50 text-red-300' :
                                            strat.risk_level === 'Moderate' ? 'bg-yellow-900/50 text-yellow-300' :
                                                'bg-green-900/50 text-green-300'
                                            }`}>
                                            {strat.risk_level}
                                        </span>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}
        </div>
    );
};

export default ReActDashboard;
