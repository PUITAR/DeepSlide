import React from 'react';
import { motion, Reorder } from 'framer-motion';
import type { LogicNode } from './types';
import { GripVertical, Trash2 } from 'lucide-react';
import clsx from 'clsx';
import useMeasure from 'react-use-measure';

interface NodeCardProps {
  node: LogicNode;
  index: number;
  isSelected: boolean;
  isProcessing?: boolean;
  onSelect: (id: string) => void;
  onDelete: (id: string) => void;
  onUpdateDuration: (id: string, delta: number) => void;
}

export const NodeCard = React.forwardRef<HTMLDivElement, NodeCardProps>(({ 
  node, index, isSelected, isProcessing, onSelect, onDelete, onUpdateDuration 
}, ref) => {
  const [measureRef] = useMeasure();
  
  // Combine refs
  const setRefs = (el: HTMLDivElement) => {
    measureRef(el);
    if (typeof ref === 'function') ref(el);
    else if (ref) ref.current = el;
  };

  const dMin = parseInt(node.duration?.replace(/\D/g, '') || '5');

  return (
    <Reorder.Item
      value={node}
      id={node.node_id}
      className="relative z-10"
      onPointerDown={(e) => {
        // Prevent drag when clicking controls
        if ((e.target as HTMLElement).closest('button')) {
          e.stopPropagation();
        }
      }}
    >
      <motion.div
        ref={setRefs}
        layout
        initial={{ opacity: 0, scale: 0.9 }}
        animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0, scale: 0.9 }}
        whileHover={{ y: -4 }}
        onClick={() => onSelect(node.node_id)}
        data-node-card="true"
        className={clsx(
          "w-64 p-4 rounded-2xl border bg-white shadow-sm transition-all duration-200 cursor-pointer select-none group relative",
          isProcessing
            ? "border-teal-500 ring-2 ring-teal-200 shadow-lg shadow-teal-200/70 animate-pulse"
            : isSelected
              ? "border-teal-500 ring-2 ring-teal-100 shadow-lg shadow-teal-100/50"
              : "border-slate-200 hover:border-slate-300 hover:shadow-md"
        )}
      >
        {/* Hover Actions */}
        <div className="absolute top-2 right-2 flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
          <button 
            onClick={(e) => { e.stopPropagation(); onDelete(node.node_id); }}
            className="p-1.5 rounded-lg bg-slate-50 text-slate-400 hover:text-rose-500 hover:bg-rose-50 transition-colors"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>

        {/* Header */}
        <div className="flex items-start gap-3 mb-3">
          <div className={clsx(
            "flex-none w-6 h-6 rounded-md flex items-center justify-center text-xs font-bold font-mono",
            isSelected ? "bg-teal-600 text-white" : "bg-slate-100 text-slate-500"
          )}>
            {index + 1}
          </div>
          <div className="flex-1 min-w-0 pr-6">
            <h3 className="text-sm font-semibold text-slate-900 truncate leading-tight mb-0.5">{node.title}</h3>
            <p className="text-[10px] text-slate-400 uppercase tracking-wider font-medium">{node.node_type}</p>
          </div>
        </div>

        {/* Content Preview */}
        <div className="mb-4">
          <p className="text-xs text-slate-500 line-clamp-2 leading-relaxed">
            {node.summary || 'No description'}
          </p>
        </div>

        {/* Footer / Controls */}
        <div className="flex items-center justify-between pt-3 border-t border-slate-50">
          <div className="flex items-center gap-1 bg-slate-50 rounded-lg p-1">
            <button 
              onClick={(e) => { e.stopPropagation(); onUpdateDuration(node.node_id, -1); }}
              className="w-5 h-5 flex items-center justify-center rounded text-slate-400 hover:bg-white hover:shadow-sm hover:text-teal-600 transition-all text-xs"
            >-</button>
            <div className="flex items-center gap-1 px-1 min-w-[40px] justify-center">
              <span className="text-xs font-bold text-slate-700">{dMin}</span>
              <span className="text-[10px] text-slate-400">min</span>
            </div>
            <button 
              onClick={(e) => { e.stopPropagation(); onUpdateDuration(node.node_id, 1); }}
              className="w-5 h-5 flex items-center justify-center rounded text-slate-400 hover:bg-white hover:shadow-sm hover:text-teal-600 transition-all text-xs"
            >+</button>
          </div>
          
          <div className="text-slate-300">
            <GripVertical className="h-4 w-4" />
          </div>
        </div>
      </motion.div>
    </Reorder.Item>
  );
});
