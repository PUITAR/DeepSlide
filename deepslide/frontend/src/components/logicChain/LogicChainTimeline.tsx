import React, { useMemo } from 'react';
import { Minus, Plus, Sparkles, Trash2 } from 'lucide-react';
import {
  DndContext,
  PointerSensor,
  KeyboardSensor,
  closestCenter,
  useSensor,
  useSensors,
  type DragEndEvent,
} from '@dnd-kit/core';
import {
  arrayMove,
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import clsx from 'clsx';
import type { LogicNode } from './types';
import { parseDuration, toDuration } from './types';

const SortableRow: React.FC<{
  id: string;
  node: LogicNode;
  index: number;
  selected: boolean;
  onSelect: () => void;
  onDelete: () => void;
  onDuration: (delta: number) => void;
}> = ({ id, node, index, selected, onSelect, onDelete, onDuration }) => {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id });
  const style = { transform: CSS.Transform.toString(transform), transition };
  const dmin = parseDuration(node.duration);

  return (
    <div
      ref={setNodeRef}
      style={style}
      className={clsx(
        'group rounded-xl border bg-white px-3 py-3 shadow-sm transition-colors',
        selected ? 'border-blue-300 ring-2 ring-blue-100' : 'border-slate-200 hover:border-slate-300',
        isDragging ? 'opacity-70' : 'opacity-100'
      )}
      onClick={onSelect}
    >
      <div className="flex items-start gap-3">
        <button
          type="button"
          {...attributes}
          {...listeners}
          className="mt-0.5 inline-flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-lg bg-slate-50 text-xs font-bold text-slate-700 hover:bg-slate-100"
        >
          {index + 1}
        </button>

        <div className="min-w-0 flex-1">
          <div className="truncate text-sm font-semibold text-slate-900">{node.title || 'Untitled'}</div>
          <div className="mt-0.5 line-clamp-1 text-xs text-slate-500">{node.summary || '—'}</div>
        </div>

        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onDuration(-1);
            }}
            className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-transparent bg-slate-50 text-slate-600 hover:border-slate-200 hover:bg-white"
          >
            <Minus className="h-4 w-4" />
          </button>
          <div className="w-14 text-center text-xs font-semibold text-slate-700">
            {dmin}
            <span className="ml-1 font-normal text-slate-400">min</span>
          </div>
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onDuration(1);
            }}
            className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-transparent bg-slate-50 text-slate-600 hover:border-slate-200 hover:bg-white"
          >
            <Plus className="h-4 w-4" />
          </button>

          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onDelete();
            }}
            className="ml-1 inline-flex h-8 w-8 items-center justify-center rounded-lg border border-transparent bg-white text-slate-400 hover:border-rose-200 hover:text-rose-600"
          >
            <Trash2 className="h-4 w-4" />
          </button>
        </div>
      </div>
    </div>
  );
};

export const LogicChainTimeline: React.FC<{
  items: LogicNode[];
  selectedId: string;
  onSelect: (id: string) => void;
  onReorder: (items: LogicNode[]) => void;
  onAdd: () => void;
  onDelete: (id: string) => void;
  onAutoConnect: () => void;
  onDurationChange: (id: string, nextDuration: string) => void;
}> = ({ items, selectedId, onSelect, onReorder, onAdd, onDelete, onAutoConnect, onDurationChange }) => {
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates })
  );

  const totalMin = useMemo(() => items.reduce((acc, n) => acc + parseDuration(n.duration), 0), [items]);

  const onDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    const oldIndex = items.findIndex((x) => x.node_id === active.id);
    const newIndex = items.findIndex((x) => x.node_id === over.id);
    onReorder(arrayMove(items, oldIndex, newIndex));
  };

  return (
    <div className="w-full max-w-[520px] overflow-auto rounded-2xl border border-slate-200 bg-white p-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <div className="text-sm font-semibold text-slate-900">Timeline</div>
          <div className="mt-0.5 text-xs text-slate-500">{items.length} nodes · ~{totalMin} min</div>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={onAutoConnect}
            className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50"
          >
            <Sparkles className="h-4 w-4" />
            Auto
          </button>
          <button
            type="button"
            onClick={onAdd}
            className="inline-flex items-center gap-2 rounded-xl bg-teal-600 px-3 py-2 text-sm font-semibold text-white hover:bg-teal-700"
          >
            <Plus className="h-4 w-4" />
            Add
          </button>
        </div>
      </div>

      <div className="mt-3 space-y-2">
        <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={onDragEnd}>
          <SortableContext items={items.map((n) => n.node_id)} strategy={verticalListSortingStrategy}>
            {items.map((node, i) => (
              <SortableRow
                key={node.node_id}
                id={node.node_id}
                node={node}
                index={i}
                selected={node.node_id === selectedId}
                onSelect={() => onSelect(node.node_id)}
                onDelete={() => onDelete(node.node_id)}
                onDuration={(delta) => {
                  const cur = parseDuration(node.duration);
                  onDurationChange(node.node_id, toDuration(cur + delta));
                }}
              />
            ))}
          </SortableContext>
        </DndContext>
      </div>
    </div>
  );
};
