import React from 'react';
import { Loader2 } from 'lucide-react';
import { useProjectStore } from '../store/useProjectStore';

export const GlobalBusyOverlay: React.FC = () => {
  const { busyLabel, busyProgress } = useProjectStore();
  if (!busyLabel) return null;

  return (
    <div className="fixed inset-0 z-[100] pointer-events-none">
      <div className="absolute inset-0 bg-white/10" />
      <div className="absolute bottom-6 left-1/2 -translate-x-1/2 rounded-2xl bg-white/85 px-4 py-3 shadow-xl ring-1 ring-white/60 min-w-[200px] flex flex-col items-center gap-2">
        <div className="flex items-center gap-3">
          <Loader2 className="h-4 w-4 animate-spin text-teal-600" />
          <div className="text-sm font-semibold text-slate-800">{busyLabel}</div>
        </div>
        {typeof busyProgress === 'number' ? (
          <div className="w-full max-w-[320px]">
            <div className="h-1.5 w-full rounded-full bg-slate-200 overflow-hidden">
              <div className="h-full bg-teal-600 transition-[width] duration-200" style={{ width: `${Math.max(0, Math.min(100, busyProgress))}%` }} />
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
};
