import React, { useMemo } from 'react';
import { ChevronLeft } from 'lucide-react';
import clsx from 'clsx';
import { useProjectStore } from '../store/useProjectStore';

type StepItem = {
  key: string;
  label: string;
  state: 'REQUIREMENTS' | 'LOGIC_CHAIN' | 'EDITING' | 'PREVIEW';
};

const steps: StepItem[] = [
  { key: 'req', label: 'Requirements', state: 'REQUIREMENTS' },
  { key: 'logic', label: 'Logic Chain', state: 'LOGIC_CHAIN' },
  { key: 'edit', label: 'Slide Editor', state: 'EDITING' },
  { key: 'preview', label: 'Preview & Export', state: 'PREVIEW' },
];

const orderIndex = (s: string) => {
  if (s === 'REQUIREMENTS') return 1;
  if (s === 'LOGIC_CHAIN') return 2;
  if (s === 'EDITING') return 3;
  if (s === 'PREVIEW') return 4;
  return 0;
};

export const StageNav: React.FC<{
  title?: string;
  rightContent?: React.ReactNode;
}> = ({ title, rightContent }) => {
  const { appState, currentProject, navigateTo } = useProjectStore();

  const currentIdx = useMemo(() => orderIndex(appState), [appState]);
  const canGoBack = useMemo(() => currentIdx > 1, [currentIdx]);

  if (!currentProject) return null;
  if (appState === 'UPLOAD') return null;

  const onBack = async () => {
    if (!canGoBack) return;
    const prev = steps[Math.max(0, currentIdx - 2)];
    await navigateTo(prev.state);
  };

  return (
    <div className="flex-none sticky top-0 z-50 border-b border-white/50 bg-white/90 backdrop-blur-md">
      <div className="mx-auto flex h-14 w-full items-center gap-4 px-4 justify-between">
        {/* Left: Logo & Title */}
        <div className="flex items-center gap-3 min-w-0">
          <button
            type="button"
            onClick={onBack}
            disabled={!canGoBack}
            className={clsx(
              'inline-flex h-9 w-9 items-center justify-center rounded-xl transition-colors shrink-0',
              canGoBack ? 'text-slate-600 hover:bg-slate-100' : 'text-slate-300'
            )}
            aria-label="Go back"
          >
            <ChevronLeft className="h-5 w-5" />
          </button>
          
          <div className="flex items-center gap-3 min-w-0">
            <div className="flex items-center gap-2 shrink-0">
              <div className="h-8 w-8 rounded-lg bg-white border border-slate-200 shadow-sm overflow-hidden">
                <img src="/api/v1/assets/logo.jpg" alt="DeepSlide" className="h-full w-full object-cover" />
              </div>
              <div className="hidden md:block text-sm font-bold text-slate-900">DeepSlide</div>
            </div>
            
            {title && (
              <>
                <div className="h-4 w-px bg-slate-200 mx-1 shrink-0" />
                <div className="min-w-0">
                  <div className="truncate text-sm font-medium text-slate-600 max-w-[200px]">{title}</div>
                </div>
              </>
            )}
          </div>
        </div>

        {/* Center: Steps (Hidden on small screens, simplified) */}
        <div className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 hidden lg:flex items-center justify-center">
          <div className="flex items-center gap-1 rounded-full bg-slate-100/50 px-1.5 py-1 shadow-sm ring-1 ring-slate-200/50 backdrop-blur-sm">
          {steps.map((s, idx) => {
            const stepIdx = idx + 1;
            const active = stepIdx === currentIdx;
            const enabled = stepIdx <= currentIdx;
            return (
              <button
                key={s.key}
                type="button"
                onClick={() => enabled && navigateTo(s.state)}
                disabled={!enabled}
                className={clsx(
                  'px-3 py-1 text-[11px] font-semibold transition-all rounded-full flex items-center gap-1.5',
                  active ? 'bg-white text-teal-700 shadow-sm ring-1 ring-slate-200' : enabled ? 'text-slate-500 hover:text-slate-900' : 'text-slate-300'
                )}
              >
                <span className={clsx('inline-flex h-4 w-4 items-center justify-center rounded-full text-[9px]', active ? 'bg-teal-100 text-teal-700' : enabled ? 'bg-slate-200 text-slate-500' : 'bg-slate-100 text-slate-300')}>
                  {stepIdx}
                </span>
                {s.label}
              </button>
            );
          })}
          </div>
        </div>

        {/* Right: Actions */}
        <div className="flex items-center justify-end gap-2 min-w-0">
          {rightContent}
        </div>
      </div>
    </div>
  );
};
