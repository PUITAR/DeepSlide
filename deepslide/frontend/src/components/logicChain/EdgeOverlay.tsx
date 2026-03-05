import React from 'react';
import type { LogicEdge } from './types';

interface EdgeOverlayProps {
  edges: LogicEdge[];
  nodeBounds: Map<string, DOMRect>;
  onDeleteEdge: (idx: number) => void;
}

export const EdgeOverlay: React.FC<EdgeOverlayProps> = ({ edges, nodeBounds, onDeleteEdge }) => {
  // Filter only reference edges
  const refs = edges.map((e, i) => ({ ...e, idx: i })).filter(e => e.type === 'reference');

  const getPath = (fromId: string, toId: string, laneIdx: number) => {
    const r1 = nodeBounds.get(fromId);
    const r2 = nodeBounds.get(toId);
    if (!r1 || !r2) return '';

    // Relative to parent container (which should be positioned relative)
    // Actually, nodeBounds are usually viewport relative if using getBoundingClientRect
    // We need coordinates relative to the SVG container.
    // Assuming SVG is absolute 0,0 inside the scrollable container.
    // We need to pass offset or ensure bounds are correct.
    // For simplicity, let's assume the parent container is the offset parent.
    
    const x1 = r1.left + r1.width / 2;
    const y1 = r1.top + r1.height; // Bottom center
    const x2 = r2.left + r2.width / 2;
    const y2 = r2.top + r2.height; // Bottom center

    const laneY = Math.max(y1, y2) + 40 + (laneIdx * 30);
    const dir = x2 > x1 ? 1 : -1;
    const r = 12; // corner radius

    return `M ${x1} ${y1} 
            L ${x1} ${laneY - r} 
            Q ${x1} ${laneY} ${x1 + dir * r} ${laneY}
            L ${x2 - dir * r} ${laneY}
            Q ${x2} ${laneY} ${x2} ${laneY - r}
            L ${x2} ${y2}`;
  };

  // Basic lane packing logic (very simple)
  const lanes: Array<Array<[number, number]>> = [];
  const edgePaths = refs.map(e => {
    const r1 = nodeBounds.get(e.from);
    const r2 = nodeBounds.get(e.to);
    if (!r1 || !r2) return null;
    
    // Use center X for interval check to allow tighter packing
    const start = Math.min(r1.left + r1.width/2, r2.left + r2.width/2);
    const end = Math.max(r1.left + r1.width/2, r2.left + r2.width/2);
    
    // Find first lane where this interval doesn't overlap
    // Add small buffer to avoid touching lines
    let lane = lanes.findIndex(l => !l.some(([s, e]) => start < e + 10 && end > s - 10));
    if (lane === -1) {
      lane = lanes.length;
      lanes.push([]);
    }
    lanes[lane].push([start, end]);
    
    const x1 = r1.left + r1.width / 2;
    const y1 = r1.top + r1.height;
    const x2 = r2.left + r2.width / 2;
    const y2 = r2.top + r2.height;
    const laneY = Math.max(y1, y2) + 40 + (lane * 30);
    const reason = String(e.reason || '').trim();

    return {
      d: getPath(e.from, e.to, lane),
      edge: e,
      cx: x1 + (x2 > x1 ? 20 : -20),
      cy: laneY - 20,
      reason,
      labelX: (x1 + x2) / 2,
      labelY: laneY + 18,
      labelW: Math.min(320, Math.max(80, 20 + reason.length * 6)),
    };
  }).filter(Boolean);

  return (
    <svg className="absolute inset-0 w-full h-full pointer-events-none overflow-visible z-0">
      <defs>
        <marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
          <path d="M 0 0 L 10 5 L 0 10 z" fill="#6366f1" />
        </marker>
        <linearGradient id="edge-grad" x1="0%" y1="0%" x2="100%" y2="0%">
          <stop offset="0%" stopColor="#6366f1" />
          <stop offset="100%" stopColor="#8b5cf6" />
        </linearGradient>
      </defs>
      
      {edgePaths.map((ep, i) => (
        <g key={i} className="group pointer-events-auto">
          {/* Hit area */}
          <path d={ep?.d} stroke="transparent" strokeWidth="20" fill="none" className="cursor-pointer" />
          {/* Visible line */}
          <path 
            d={ep?.d} 
            stroke="url(#edge-grad)" 
            strokeWidth="2" 
            fill="none" 
            markerEnd="url(#arrow)"
            strokeDasharray="8 4"
            className="opacity-60 group-hover:opacity-100 transition-opacity"
          >
            {ep?.reason ? <title>{ep.reason}</title> : null}
            <animate attributeName="stroke-dashoffset" from="24" to="0" dur="1s" repeatCount="indefinite" />
          </path>

          {ep?.reason ? (
            <g
              transform={`translate(${ep.labelX}, ${ep.labelY})`}
              className="opacity-0 group-hover:opacity-100 transition-opacity"
            >
              <rect x={-(ep.labelW / 2)} y={0} width={ep.labelW} height={22} rx={11} fill="white" stroke="#e2e8f0" />
              <text textAnchor="middle" y={14} fontSize="10" fill="#334155">
                {ep.reason.length > 40 ? `${ep.reason.slice(0, 40)}…` : ep.reason}
              </text>
            </g>
          ) : null}
          
          {/* Delete Button (appears on hover) */}
          <g 
            transform={`translate(${ep?.cx}, ${ep?.cy})`} 
            className="opacity-0 group-hover:opacity-100 transition-opacity cursor-pointer"
            onClick={() => onDeleteEdge(ep!.edge.idx)}
          >
            <circle r="10" fill="white" stroke="#e2e8f0" />
            <text textAnchor="middle" dy="4" fontSize="10" fill="#ef4444">✕</text>
          </g>
        </g>
      ))}
    </svg>
  );
};
