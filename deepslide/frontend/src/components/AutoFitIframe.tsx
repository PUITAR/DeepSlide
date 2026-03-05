import React, { useEffect, useRef } from 'react';
import clsx from 'clsx';
import type { SlideThemePreset } from './SlideThemeSelector';

type Props = {
  src: string;
  className?: string;
  title?: string;
  themePreset?: SlideThemePreset;
};

const THEME_PRESETS: Record<SlideThemePreset, { dataTheme: 'light' | 'dark'; classes: string[]; css: string }> = {
  'modern-glass': {
    dataTheme: 'light',
    classes: ['theme-glass', 'accent-cyan', 'hl-aurora', 'motion-low'],
    css: `
      :root {
        --bg-core: #f8fafc;
        --bg-card: rgba(255, 255, 255, 0.85);
        --bg-card-hover: rgba(255, 255, 255, 0.98);
        --text-main: #0f172a;
        --text-muted: #475569;
        --border-soft: rgba(15, 23, 42, 0.12);
        --accent-primary: #06b6d4;
      }
      body { background: var(--bg-core); }
    `,
  },
  'high-contrast-dark': {
    dataTheme: 'dark',
    classes: ['theme-glass', 'accent-emerald', 'hl-underline', 'motion-low'],
    css: `
      :root {
        --bg-core: #06070b;
        --bg-card: rgba(10, 12, 19, 0.9);
        --bg-card-hover: rgba(15, 18, 28, 0.95);
        --text-main: rgba(248, 250, 252, 0.98);
        --text-muted: rgba(148, 163, 184, 0.9);
        --border-soft: rgba(148, 163, 184, 0.18);
        --accent-primary: #34d399;
      }
      .card { box-shadow: 0 24px 60px -30px rgba(0, 0, 0, 0.85); }
    `,
  },
  'bento-dashboard': {
    dataTheme: 'light',
    classes: ['theme-bento', 'accent-purple', 'hl-violet', 'motion-low'],
    css: `
      :root {
        --bg-core: #f7f5ff;
        --bg-card: rgba(255, 255, 255, 0.95);
        --bg-card-hover: #ffffff;
        --text-main: #1f2937;
        --text-muted: #6b7280;
        --border-soft: rgba(99, 102, 241, 0.18);
        --accent-primary: #6366f1;
      }
      .theme-bento .card {
        border-radius: 24px;
        border: 1px solid rgba(99, 102, 241, 0.18);
        box-shadow: 0 18px 40px -26px rgba(79, 70, 229, 0.35);
      }
      .theme-bento .card:hover { transform: translateY(-2px); }
      .theme-bento .metrics { gap: 18px; }
    `,
  },
  'neon-cyber': {
    dataTheme: 'dark',
    classes: ['theme-neon', 'accent-cyan', 'hl-cyber', 'motion-high'],
    css: `
      :root {
        --bg-core: #05060b;
        --bg-card: rgba(7, 9, 16, 0.9);
        --bg-card-hover: rgba(12, 16, 30, 0.95);
        --text-main: rgba(240, 249, 255, 0.98);
        --text-muted: rgba(148, 163, 184, 0.8);
        --border-soft: rgba(56, 189, 248, 0.25);
        --accent-primary: #22d3ee;
      }
      .theme-neon .card {
        border: 1px solid rgba(34, 211, 238, 0.35);
        box-shadow: 0 0 30px rgba(34, 211, 238, 0.18), 0 24px 60px -30px rgba(0, 0, 0, 0.85);
      }
      .theme-neon .card::after { opacity: 0.12; }
    `,
  },
  'minimal-slate': {
    dataTheme: 'light',
    classes: ['theme-glass', 'accent-primary', 'hl-underline', 'motion-low'],
    css: `
      :root {
        --bg-core: #f8fafc;
        --bg-card: #ffffff;
        --bg-card-hover: #ffffff;
        --text-main: #0f172a;
        --text-muted: #475569;
        --border-soft: rgba(15, 23, 42, 0.08);
        --accent-primary: #2563eb;
      }
      .card { box-shadow: 0 12px 30px -24px rgba(15, 23, 42, 0.35); }
    `,
  },
  'midnight-contrast': {
    dataTheme: 'dark',
    classes: ['theme-neon', 'accent-purple', 'hl-violet', 'motion-low'],
    css: `
      :root {
        --bg-core: #050505;
        --bg-card: rgba(13, 15, 26, 0.92);
        --bg-card-hover: rgba(18, 22, 36, 0.98);
        --text-main: rgba(248, 250, 252, 0.98);
        --text-muted: rgba(148, 163, 184, 0.85);
        --border-soft: rgba(139, 92, 246, 0.25);
        --accent-primary: #8b5cf6;
      }
      .card { box-shadow: 0 20px 50px -30px rgba(0, 0, 0, 0.9); }
    `,
  },
  'solar-warm': {
    dataTheme: 'light',
    classes: ['theme-glass', 'accent-orange', 'hl-sunset', 'motion-low'],
    css: `
      :root {
        --bg-core: #fff7ed;
        --bg-card: rgba(255, 255, 255, 0.92);
        --bg-card-hover: #ffffff;
        --text-main: #1f2937;
        --text-muted: #6b7280;
        --border-soft: rgba(251, 146, 60, 0.18);
        --accent-primary: #f97316;
      }
      .card { box-shadow: 0 18px 40px -28px rgba(249, 115, 22, 0.35); }
    `,
  },
  'ocean-blue': {
    dataTheme: 'light',
    classes: ['theme-glass', 'accent-cyan', 'hl-aurora', 'motion-low'],
    css: `
      :root {
        --bg-core: #eef7ff;
        --bg-card: rgba(255, 255, 255, 0.9);
        --bg-card-hover: #ffffff;
        --text-main: #0f172a;
        --text-muted: #475569;
        --border-soft: rgba(6, 182, 212, 0.2);
        --accent-primary: #0ea5e9;
      }
    `,
  },
  'graphite': {
    dataTheme: 'dark',
    classes: ['theme-glass', 'accent-primary', 'hl-mono', 'motion-low'],
    css: `
      :root {
        --bg-core: #0b0d10;
        --bg-card: rgba(17, 21, 26, 0.92);
        --bg-card-hover: rgba(21, 26, 34, 0.98);
        --text-main: rgba(241, 245, 249, 0.96);
        --text-muted: rgba(148, 163, 184, 0.75);
        --border-soft: rgba(148, 163, 184, 0.2);
        --accent-primary: #94a3b8;
      }
    `,
  },
  'rose-light': {
    dataTheme: 'light',
    classes: ['theme-glass', 'accent-purple', 'hl-violet', 'motion-low'],
    css: `
      :root {
        --bg-core: #fff1f2;
        --bg-card: rgba(255, 255, 255, 0.94);
        --bg-card-hover: #ffffff;
        --text-main: #1f2937;
        --text-muted: #6b7280;
        --border-soft: rgba(244, 114, 182, 0.18);
        --accent-primary: #ec4899;
      }
    `,
  },
};

const buildThemeCss = (preset: SlideThemePreset) => {
  const base = THEME_PRESETS[preset]?.css || '';
  return `
    ${base}
    .motion-low .animate-in { animation-duration: 0.5s; }
    .motion-high .animate-in { animation-duration: 0.85s; animation-timing-function: cubic-bezier(0.12, 0.84, 0.18, 1); }
    .theme-neon .keynote-highlight.k1 { text-shadow: 0 0 28px rgba(34, 211, 238, 0.35); }
  `;
};

export const AutoFitIframe: React.FC<Props> = ({ src, className, title, themePreset = 'modern-glass' }) => {
  const ref = useRef<HTMLIFrameElement | null>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    const applyTheme = () => {
      try {
        const doc = el.contentDocument;
        if (!doc) return;
        const body = doc.body;
        if (!body) return;

        const preset = THEME_PRESETS[themePreset] || THEME_PRESETS['modern-glass'];
        body.setAttribute('data-theme', preset.dataTheme);
        const classes = new Set(body.className.split(' ').filter(Boolean));
        for (const c of Array.from(classes)) {
          if (c.startsWith('theme-') || c.startsWith('accent-') || c.startsWith('hl-') || c.startsWith('motion-')) {
            classes.delete(c);
          }
        }
        preset.classes.forEach((c) => classes.add(c));
        body.className = Array.from(classes).join(' ');

        const styleId = '__deepslide_theme__';
        let style = doc.getElementById(styleId) as HTMLStyleElement | null;
        if (!style) {
          style = doc.createElement('style');
          style.id = styleId;
          doc.head.appendChild(style);
        }
        style.textContent = buildThemeCss(themePreset);
      } catch {
        return;
      }
    };

    const applyScale = () => {
      try {
        const doc = el.contentDocument;
        if (!doc) return;
        const html = doc.documentElement;
        const body = doc.body;
        if (!html || !body) return;

        const styleId = '__deepslide_fit__';
        let style = doc.getElementById(styleId) as HTMLStyleElement | null;
        if (!style) {
          style = doc.createElement('style');
          style.id = styleId;
          doc.head.appendChild(style);
        }

        body.setAttribute('data-mode', 'preview');

        style.textContent =
          'html,body{height:auto;overflow:visible} body{margin:0;transform:none!important;width:auto!important;min-height:auto!important} img,svg,canvas{max-width:100%;height:auto} svg{display:block}';

        const slide = doc.querySelector('.slide') as HTMLElement | null;
        const sw = slide ? Math.max(slide.scrollWidth || 0, slide.offsetWidth || 0) : Math.max(html.scrollWidth || 0, body.scrollWidth || 0);
        const sh = slide ? Math.max(slide.scrollHeight || 0, slide.offsetHeight || 0) : Math.max(html.scrollHeight || 0, body.scrollHeight || 0);
        const cw = el.clientWidth || 1;
        const ch = el.clientHeight || 1;
        let scale = Math.min(cw / Math.max(1, sw), ch / Math.max(1, sh));
        scale = Math.max(0.1, Math.min(2.0, scale));
        scale = Math.round(scale * 1000) / 1000;

        style.textContent = `html,body{height:100%;overflow:hidden} body{margin:0;transform-origin:0 0;transform:scale(${scale});width:${100 / scale}%;min-height:${100 / scale}%;overflow:hidden} img,svg,canvas{max-width:100%;height:auto} svg{display:block}`;
      } catch {
        return;
      }
    };

    const onLoad = () => {
      applyTheme();
      applyScale();
      window.setTimeout(applyScale, 80);
      window.setTimeout(applyScale, 250);
      window.setTimeout(applyScale, 700);
      try {
        const doc = el.contentDocument;
        const fonts = (doc as unknown as Document & { fonts?: FontFaceSet }).fonts;
        fonts?.ready?.then(() => applyScale());
      } catch {
        // ignore
      }
    };

    const ro = new ResizeObserver(() => applyScale());
    ro.observe(el);
    window.addEventListener('resize', applyScale);
    el.addEventListener('load', onLoad);

    let mo: MutationObserver | null = null;
    const bindMutationObserver = () => {
      try {
        const doc = el.contentDocument;
        if (!doc || !doc.body) return;
        let t: number | null = null;
        mo = new MutationObserver(() => {
          if (t) window.clearTimeout(t);
          t = window.setTimeout(() => applyScale(), 50);
        });
        mo.observe(doc.body, { childList: true, subtree: true, attributes: true, characterData: false });
      } catch {
        // ignore
      }
    };
    el.addEventListener('load', bindMutationObserver);

    return () => {
      ro.disconnect();
      window.removeEventListener('resize', applyScale);
      el.removeEventListener('load', onLoad);
      el.removeEventListener('load', bindMutationObserver);
      if (mo) mo.disconnect();
    };
  }, [src, themePreset]);

  return (
    <iframe
      ref={ref}
      title={title || 'HTML Preview'}
      src={src}
      className={clsx('bg-white', className)}
      scrolling="yes"
      sandbox="allow-scripts allow-same-origin"
    />
  );
};
