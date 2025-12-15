import React, { useState, useEffect, useMemo } from 'react';

const MatrixEditor = ({ sessionId = "default-session" }) => {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [finalChain, setFinalChain] = useState(null);
  const [explaining, setExplaining] = useState(false);
  const [showGraph, setShowGraph] = useState(true);
  const [posOverride, setPosOverride] = useState({});
  const [dragging, setDragging] = useState(null);
  const [scale, setScale] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [panning, setPanning] = useState(false);
  const [lastPointer, setLastPointer] = useState(null);
  const [selectedNode, setSelectedNode] = useState(null);
  const [selectedEdge, setSelectedEdge] = useState(null);

  // API Base URL - adjust if running via proxy or direct
  // Assuming the standalone api_server.py is running on port 8002
  const API_BASE = "http://localhost:8002"; 

  useEffect(() => {
    fetchSession();
  }, [sessionId]);

  const fetchSession = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/presenter/session/${sessionId}`);
      if (!res.ok) throw new Error("Failed to load session");
      const json = await res.json();
      setData(json);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleCellChange = (rowIndex, colIndex, value) => {
    if (!data) return;
    const newMatrix = [...data.matrix];
    newMatrix[rowIndex] = [...newMatrix[rowIndex]];
    newMatrix[rowIndex][colIndex] = value;
    setData({ ...data, matrix: newMatrix });
  };

  const handleSave = async () => {
    if (!data) return;
    setSaving(true);
    try {
      const res = await fetch(`${API_BASE}/api/presenter/matrix/${sessionId}/update`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ matrix: data.matrix })
      });
      if (!res.ok) throw new Error("Failed to save");
      alert("Saved successfully!");
    } catch (err) {
      alert("Error saving: " + err.message);
    } finally {
      setSaving(false);
    }
  };

  const handleConfirm = async () => {
    if (!data) return;
    setConfirming(true);
    try {
      const res = await fetch(`${API_BASE}/api/presenter/matrix/${sessionId}/confirm`, {
        method: "POST"
      });
      if (!res.ok) throw new Error("Failed to confirm");
      const json = await res.json();
      setFinalChain(json);
    } catch (err) {
      alert("Error confirming: " + err.message);
    } finally {
      setConfirming(false);
    }
  };

  const handleExplain = async () => {
    setExplaining(true);
    try {
      const res = await fetch(`${API_BASE}/api/presenter/matrix/${sessionId}/explain`, {
        method: "POST"
      });
      if (!res.ok) throw new Error("Failed to explain");
      const json = await res.json();
      setFinalChain(json);
    } catch (err) {
      alert("Error explaining: " + err.message);
    } finally {
      setExplaining(false);
    }
  };

  if (loading && !data) return <div className="p-4">Loading matrix...</div>;
  if (error) return <div className="p-4 text-red-500">Error: {error}. Make sure api_server.py is running on port 8002.</div>;
  if (!data) return null;

  const { nodes, matrix } = data;

  const edges = useMemo(() => {
    const list = [];
    for (let i = 0; i < matrix.length; i++) {
      for (let j = 0; j < matrix[i].length; j++) {
        if (i !== j && matrix[i][j]) {
          list.push({ fromIndex: i, toIndex: j });
        }
      }
    }
    return list;
  }, [matrix]);

  const layout = useMemo(() => {
    const count = nodes.length;
    const W = 1000;
    const H = 560;
    const cx = W / 2;
    const cy = H / 2;
    const r = Math.min(W, H) / 2 - 80;
    const positions = nodes.map((_, idx) => {
      const angle = (2 * Math.PI * idx) / count - Math.PI / 2;
      const x = cx + r * Math.cos(angle);
      const y = cy + r * Math.sin(angle);
      return { x, y };
    });
    return { W, H, positions };
  }, [nodes]);

  const getPos = (i) => (posOverride[i] ? posOverride[i] : layout.positions[i]);

  const onWheel = (e) => {
    e.preventDefault();
    const delta = e.deltaY > 0 ? -0.1 : 0.1;
    setScale((s) => Math.min(2, Math.max(0.5, s + delta)));
  };

  const onSvgMouseDown = (e) => {
    if (dragging !== null) return;
    setPanning(true);
    setLastPointer({ x: e.clientX, y: e.clientY });
  };

  const onSvgMouseMove = (e) => {
    if (dragging !== null) {
      const bbox = e.currentTarget.getBoundingClientRect();
      const x = (e.clientX - bbox.left - pan.x) / scale;
      const y = (e.clientY - bbox.top - pan.y) / scale;
      setPosOverride((prev) => ({ ...prev, [dragging]: { x, y } }));
    } else if (panning && lastPointer) {
      const dx = e.clientX - lastPointer.x;
      const dy = e.clientY - lastPointer.y;
      setPan((p) => ({ x: p.x + dx, y: p.y + dy }));
      setLastPointer({ x: e.clientX, y: e.clientY });
    }
  };

  const onSvgMouseUp = () => {
    setDragging(null);
    setPanning(false);
    setLastPointer(null);
  };

  return (
    <div className="p-6 max-w-full overflow-x-auto">
      <h2 className="text-2xl font-bold mb-4">Logic Connection Matrix</h2>
      <p className="mb-4 text-gray-600">
        Edit the logical connections between speech paragraphs (nodes).
        Rows represent source nodes, Columns represent target nodes.
      </p>

      <div className="flex gap-4 mb-4 items-center">
        <button 
          onClick={handleSave}
          disabled={saving}
          className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
        >
          {saving ? "Saving..." : "Save Changes"}
        </button>
        <button 
          onClick={fetchSession}
          className="px-4 py-2 bg-gray-200 text-gray-800 rounded hover:bg-gray-300"
        >
          Reload
        </button>
        <button
          onClick={handleConfirm}
          disabled={confirming}
          className="px-4 py-2 bg-green-600 text-white rounded hover:bg-green-700 disabled:opacity-50"
        >
          {confirming ? "Confirming..." : "Confirm Final Chain"}
        </button>
        <button
          onClick={handleExplain}
          disabled={explaining}
          className="px-4 py-2 bg-purple-600 text-white rounded hover:bg-purple-700 disabled:opacity-50"
        >
          {explaining ? "Explaining..." : "Explain Relationships"}
        </button>
        <label className="ml-auto inline-flex items-center gap-2 text-sm text-gray-600">
          <input type="checkbox" checked={showGraph} onChange={(e) => setShowGraph(e.target.checked)} />
          Graph View
        </label>
      </div>

      <div className="border rounded shadow-sm overflow-hidden">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider sticky left-0 bg-gray-50 z-10 border-b">
                Nodes
              </th>
              {nodes.map((node, i) => (
                <th key={i} className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider min-w-[150px] border-b border-l">
                  {i + 1}. {node.length > 20 ? node.substring(0, 20) + '...' : node}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-gray-200">
            {nodes.map((rowNode, i) => (
              <tr key={i}>
                <td className="px-3 py-2 whitespace-nowrap text-sm font-medium text-gray-900 sticky left-0 bg-white z-10 border-r border-b">
                  {i + 1}. {rowNode}
                </td>
                {matrix[i].map((cell, j) => (
                  <td key={j} className="px-1 py-1 border-l border-b border-gray-100 relative">
                    {i === j ? (
                      <div className="text-center text-xs text-gray-400">—</div>
                    ) : (
                      <label className="flex items-center justify-center gap-2">
                        <input
                          type="checkbox"
                          checked={Boolean(cell)}
                          onChange={(e) => handleCellChange(i, j, e.target.checked ? "✓" : "")}
                        />
                      </label>
                    )}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {showGraph && (
        <div className="mt-8">
          <h3 className="text-xl font-semibold mb-2">Relationship Graph</h3>
          <p className="text-gray-600 mb-3">Visual preview of selected connections.</p>
          <div className="rounded-lg border border-gray-200 bg-white">
            <svg
              width={layout.W}
              height={layout.H}
              className="block cursor-move"
              onWheel={onWheel}
              onMouseDown={onSvgMouseDown}
              onMouseMove={onSvgMouseMove}
              onMouseUp={onSvgMouseUp}
            >
              <defs>
                <marker id="arrow" viewBox="0 0 10 10" refX="10" refY="5" markerUnits="strokeWidth" markerWidth="8" markerHeight="8" orient="auto-start-reverse">
                  <path d="M 0 0 L 10 5 L 0 10 z" fill="#6366f1" />
                </marker>
              </defs>
              <g transform={`translate(${pan.x} ${pan.y}) scale(${scale})`}>
              {edges.map((e, idx) => {
                const from = getPos(e.fromIndex);
                const to = getPos(e.toIndex);
                const dx = to.x - from.x;
                const dy = to.y - from.y;
                const mx = from.x + dx * 0.5;
                const my = from.y + dy * 0.5;
                const curve = 0.15;
                const cx1 = from.x + dy * curve;
                const cy1 = from.y - dx * curve;
                const cx2 = to.x + dy * curve * 0.2;
                const cy2 = to.y - dx * curve * 0.2;
                return (
                  <path
                    key={idx}
                    d={`M ${from.x} ${from.y} C ${cx1} ${cy1}, ${cx2} ${cy2}, ${to.x} ${to.y}`}
                    stroke={selectedEdge && selectedEdge.index === idx ? "#ef4444" : "#6366f1"}
                    strokeWidth={selectedEdge && selectedEdge.index === idx ? 3 : 2}
                    fill="none"
                    markerEnd="url(#arrow)"
                    opacity={0.85}
                    onClick={() => setSelectedEdge({ index: idx, from: e.fromIndex, to: e.toIndex })}
                  />
                );
              })}
              {nodes.map((_, i) => {
                const p = getPos(i);
                return (
                  <g
                    key={i}
                    transform={`translate(${p.x}, ${p.y})`}
                    onMouseDown={(e) => { e.stopPropagation(); setDragging(i); setSelectedNode(i); }}
                  >
                    <circle r={selectedNode === i ? 26 : 24} fill="#f1f5f9" stroke={selectedNode === i ? "#6366f1" : "#cbd5e1"} strokeWidth={2} />
                    <text x={0} y={4} textAnchor="middle" fontSize={12} fill="#0f172a">{i + 1}</text>
                  </g>
                );
              })}
              </g>
            </svg>
            <div className="px-5 py-4 grid grid-cols-4 gap-4">
              {nodes.map((n, i) => (
                <div key={i} className="flex items-center gap-2 text-sm text-gray-700">
                  <span className="inline-flex items-center justify-center w-6 h-6 rounded-full bg-indigo-100 text-indigo-700 border border-indigo-200">{i + 1}</span>
                  <span className="truncate" title={n}>{n}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {finalChain && (
        <div className="mt-6">
          <h3 className="text-xl font-semibold mb-2">Final Logic Chain</h3>
          <p className="text-gray-600 mb-2">Confirmed relationships:</p>
          <ul className="list-disc ml-6">
            {finalChain.edges.length === 0 && (
              <li className="text-gray-500">No relationships selected.</li>
            )}
            {finalChain.edges.map((e, idx) => (
              <li key={idx}>
                [{e.from_index + 1}] {e.from} → [{e.to_index + 1}] {e.to}{e.reason ? ` (${e.reason})` : ""}{e.detail ? `：${e.detail}` : ""}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
};

export default MatrixEditor;
