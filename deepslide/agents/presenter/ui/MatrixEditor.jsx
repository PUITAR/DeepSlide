import React, { useState, useEffect } from 'react';

const MatrixEditor = ({ sessionId = "default-session" }) => {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [finalChain, setFinalChain] = useState(null);
  const [explaining, setExplaining] = useState(false);

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

  return (
    <div className="p-6 max-w-full overflow-x-auto">
      <h2 className="text-2xl font-bold mb-4">Logic Connection Matrix</h2>
      <p className="mb-4 text-gray-600">
        Edit the logical connections between speech paragraphs (nodes).
        Rows represent source nodes, Columns represent target nodes.
      </p>

      <div className="flex gap-4 mb-4">
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
