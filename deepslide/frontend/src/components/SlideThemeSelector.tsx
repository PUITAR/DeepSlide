import React from 'react';
import clsx from 'clsx';

export type SlideThemePreset =
  | 'modern-glass'
  | 'high-contrast-dark'
  | 'bento-dashboard'
  | 'neon-cyber'
  | 'minimal-slate'
  | 'midnight-contrast'
  | 'solar-warm'
  | 'ocean-blue'
  | 'graphite'
  | 'rose-light';

type PresetOption = { value: SlideThemePreset; label: string; description: string };

const OPTIONS: PresetOption[] = [
  { value: 'modern-glass', label: 'Modern Glass', description: 'Clean, premium, balanced contrast' },
  { value: 'high-contrast-dark', label: 'High Contrast', description: 'Sharp text, projector-friendly' },
  { value: 'bento-dashboard', label: 'Bento Dashboard', description: 'Card grid, data-first' },
  { value: 'neon-cyber', label: 'Neon Cyber', description: 'Bold glow, futuristic' },
  { value: 'minimal-slate', label: 'Minimal Slate', description: 'Subtle, editorial clarity' },
  { value: 'midnight-contrast', label: 'Midnight Contrast', description: 'Dark UI, crisp edges' },
  { value: 'solar-warm', label: 'Solar Warm', description: 'Warm highlights, friendly tone' },
  { value: 'ocean-blue', label: 'Ocean Blue', description: 'Cool blue, calm hierarchy' },
  { value: 'graphite', label: 'Graphite', description: 'Neutral, professional grey' },
  { value: 'rose-light', label: 'Rose Light', description: 'Soft tint, gentle emphasis' },
];

type Props = {
  value: SlideThemePreset;
  onChange: (value: SlideThemePreset) => void;
  className?: string;
};

const SlideThemeSelector: React.FC<Props> = ({ value, onChange, className }) => {
  return (
    <div className={clsx('flex flex-col gap-1', className)}>
      <div className="text-[10px] font-semibold text-slate-500 uppercase tracking-[0.18em]">Theme</div>
      <div className="relative">
        <select
          className="h-8 rounded-lg border border-slate-200 bg-white px-2 pr-7 text-xs font-semibold text-slate-700 shadow-sm hover:border-slate-300 focus:outline-none focus:ring-2 focus:ring-cyan-300/50 truncate overflow-hidden whitespace-nowrap"
          value={value}
          onChange={(e) => onChange(e.target.value as SlideThemePreset)}
        >
          {OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
        <div className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-[10px] text-slate-400">
          ▾
        </div>
      </div>
      <div className="text-[10px] text-slate-400 max-w-[140px]">{OPTIONS.find((o) => o.value === value)?.description}</div>
    </div>
  );
};

export default SlideThemeSelector;
