import React, { useRef, useState, useLayoutEffect, useMemo } from 'react';
import { Reorder } from 'framer-motion';
import type { LogicNode, LogicEdge } from './types';
import { NodeCard } from './NodeCard';
import { EdgeOverlay } from './EdgeOverlay';
import { Plus, Wand2, ZoomIn, ZoomOut, LocateFixed } from 'lucide-react';

interface LogicChainCanvasProps {
  nodes: LogicNode[];
  edges: LogicEdge[];
  onNodesChange: (nodes: LogicNode[]) => void;
  onEdgesChange: (edges: LogicEdge[]) => void;
  selectedId: string;
  onSelect: (id: string) => void;
  onAutoConnect?: () => void;
  processingNodeId?: string;
}

export const LogicChainCanvas: React.FC<LogicChainCanvasProps> = ({
  nodes, edges, onNodesChange, onEdgesChange, selectedId, onSelect, onAutoConnect, processingNodeId
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const stageRef = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const panRef = useRef({ active: false, startX: 0, startY: 0, baseX: 0, baseY: 0, pointerId: -1 });
  const [nodeBounds, setNodeBounds] = useState<Map<string, DOMRect>>(new Map());
  
  // Measure nodes
  const measureNodes = () => {
    if (!containerRef.current || !stageRef.current) return;
    const map = new Map<string, DOMRect>();
    const stageRect = stageRef.current.getBoundingClientRect();
    
    nodes.forEach(node => {
      const el = document.getElementById(node.node_id);
      if (el) {
        const rect = el.getBoundingClientRect();
        const left = (rect.left - stageRect.left) / scale;
        const top = (rect.top - stageRect.top) / scale;
        const width = rect.width / scale;
        const height = rect.height / scale;
        map.set(node.node_id, {
          ...rect,
          left,
          top,
          width,
          height
        } as DOMRect);
      }
    });
    setNodeBounds(map);
  };

  useLayoutEffect(() => {
    const raf = requestAnimationFrame(measureNodes);
    const ro = new ResizeObserver(() => requestAnimationFrame(measureNodes));
    if (containerRef.current) ro.observe(containerRef.current);
    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
    };
  }, [nodes, edges, pan.x, pan.y, scale]);

  const handleReorder = (newNodes: LogicNode[]) => {
    onNodesChange(newNodes);
    // Framer motion handles visual, but we need to update state for bounds
    setTimeout(measureNodes, 50); 
  };

  const handleAddNode = () => {
    const id = `node-${Date.now()}`;
    const newNode: LogicNode = { 
      node_id: id, 
      title: 'New Section', 
      summary: 'Description...', 
      node_type: 'section', 
      duration: '5min' 
    };
    onNodesChange([...nodes, newNode]);
    onSelect(id);
  };

  const handleDeleteNode = (id: string) => {
    onNodesChange(nodes.filter(n => n.node_id !== id));
    onEdgesChange(edges.filter(e => e.from !== id && e.to !== id));
  };

  const handleDeleteEdge = (idx: number) => {
    const newEdges = [...edges];
    newEdges.splice(idx, 1);
    onEdgesChange(newEdges);
  };

  const handleAutoConnect = () => {
    if (onAutoConnect) {
        onAutoConnect();
    }
  };

  const zoomTo = (next: number) => {
    setScale((prev) => {
      const clamped = Math.max(0.5, Math.min(2.2, next));
      return Number.isFinite(clamped) ? clamped : prev;
    });
  };

  const resetView = () => {
    setScale(1);
    setPan({ x: 0, y: 0 });
  };

  const transformStyle = useMemo(
    () => ({ transform: `translate(${pan.x}px, ${pan.y}px) scale(${scale})`, transformOrigin: '0 0' } as const),
    [pan.x, pan.y, scale]
  );

  return (
    <div className="flex flex-1 h-full overflow-hidden bg-slate-50/50 relative">
      {/* Toolbar */}
      <div className="absolute top-6 left-6 z-30 flex flex-row gap-3">
        <button onClick={handleAddNode} className="h-10 w-10 flex items-center justify-center bg-white rounded-full shadow-sm border border-slate-200 hover:text-teal-600 hover:border-teal-200 transition-all" title="Add Node">
          <Plus className="h-5 w-5" />
        </button>
        <button onClick={handleAutoConnect} className="h-10 w-10 flex items-center justify-center bg-white rounded-full shadow-sm border border-slate-200 hover:text-teal-600 hover:border-teal-200 transition-all" title="Auto Connect">
          <Wand2 className="h-5 w-5" />
        </button>
        <div className="h-10 flex items-center gap-1 bg-white rounded-full shadow-sm border border-slate-200 px-2">
          <button
            type="button"
            onClick={() => zoomTo(scale - 0.1)}
            className="h-8 w-8 rounded-full hover:bg-slate-50 text-slate-600"
            title="Zoom out"
          >
            <ZoomOut className="h-4 w-4 mx-auto" />
          </button>
          <div className="text-[11px] font-bold text-slate-600 min-w-[44px] text-center">{Math.round(scale * 100)}%</div>
          <button
            type="button"
            onClick={() => zoomTo(scale + 0.1)}
            className="h-8 w-8 rounded-full hover:bg-slate-50 text-slate-600"
            title="Zoom in"
          >
            <ZoomIn className="h-4 w-4 mx-auto" />
          </button>
          <button
            type="button"
            onClick={resetView}
            className="h-8 w-8 rounded-full hover:bg-slate-50 text-slate-600"
            title="Reset view"
          >
            <LocateFixed className="h-4 w-4 mx-auto" />
          </button>
        </div>
      </div>

      {/* Main Canvas Area */}
      <div 
        ref={containerRef}
        className="flex-1 overflow-hidden relative cursor-grab active:cursor-grabbing"
        onWheel={(e) => {
          if (!e.ctrlKey && !e.metaKey) return;
          e.preventDefault();
          const delta = e.deltaY > 0 ? -0.08 : 0.08;
          zoomTo(scale + delta);
        }}
        onPointerDown={(e) => {
          const el = e.target as HTMLElement;
          if (el.closest('[data-node-card="true"]') || el.closest('button')) return;
          panRef.current = {
            active: true,
            startX: e.clientX,
            startY: e.clientY,
            baseX: pan.x,
            baseY: pan.y,
            pointerId: e.pointerId,
          };
          (e.currentTarget as HTMLDivElement).setPointerCapture(e.pointerId);
        }}
        onPointerMove={(e) => {
          if (!panRef.current.active || panRef.current.pointerId !== e.pointerId) return;
          const dx = e.clientX - panRef.current.startX;
          const dy = e.clientY - panRef.current.startY;
          setPan({ x: panRef.current.baseX + dx, y: panRef.current.baseY + dy });
        }}
        onPointerUp={(e) => {
          if (panRef.current.pointerId !== e.pointerId) return;
          panRef.current.active = false;
          panRef.current.pointerId = -1;
        }}
      >
        <div ref={stageRef} className="w-full h-full p-10 pt-28 relative" style={transformStyle}>
          {/* Background Grid - Drawing style */}
          <div className="absolute inset-0 pointer-events-none opacity-[0.08]" 
               style={{ 
                   backgroundImage: `
                       linear-gradient(to right, #94a3b8 1px, transparent 1px),
                       linear-gradient(to bottom, #94a3b8 1px, transparent 1px)
                   `,
                   backgroundSize: '20px 20px' 
               }} 
          />

          {/* SVG Layer */}
          <EdgeOverlay 
            edges={edges} 
            nodeBounds={nodeBounds} 
            onDeleteEdge={handleDeleteEdge} 
          />

          {/* Nodes Layer */}
          <Reorder.Group 
            axis="x" 
            values={nodes} 
            onReorder={handleReorder} 
            className="flex gap-8 relative z-10 pt-10"
          >
            {nodes.map((node, index) => (
              <NodeCard
                key={node.node_id}
                node={node}
                index={index}
                isSelected={selectedId === node.node_id}
                isProcessing={!!processingNodeId && processingNodeId === node.node_id}
                onSelect={onSelect}
                onDelete={handleDeleteNode}
                onUpdateDuration={(id, delta) => {
                    const newNodes = nodes.map(n => {
                        if (n.node_id === id) {
                            const cur = parseInt(String(n.duration || '').replace(/\D/g, '') || '0');
                            const base = cur > 0 ? cur : 5;
                            return { ...n, duration: `${Math.max(1, base + delta)}min` };
                        }
                        return n;
                    });
                    onNodesChange(newNodes);
                }}
              />
            ))}
          </Reorder.Group>
        </div>
      </div>

      {/* Right Panel (Details) - Removed persistent panel */}
    </div>
  );
};
