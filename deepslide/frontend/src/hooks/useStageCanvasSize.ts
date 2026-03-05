import { useLayoutEffect, useState } from 'react';

export const useStageCanvasSize = (
  el: React.RefObject<HTMLElement | null>,
  opts?: {
    widthFactor?: number;
    heightFactor?: number;
    minWidth?: number;
    minHeight?: number;
    aspectRatio?: number;
  }
) => {
  const [size, setSize] = useState<{ width: number; height: number } | null>(null);

  useLayoutEffect(() => {
    const node = el.current;
    if (!node) return;

    const widthFactor = Math.max(0.1, Math.min(1, Number(opts?.widthFactor ?? 0.85)));
    const heightFactor = Math.max(0.1, Math.min(1, Number(opts?.heightFactor ?? 0.75)));
    const minWidth = Math.max(240, Number(opts?.minWidth ?? 320));
    const minHeight = Math.max(180, Number(opts?.minHeight ?? 240));
    const aspectRatio = Math.max(0.1, Number(opts?.aspectRatio ?? 16 / 9));

    const calc = () => {
      const rect = node.getBoundingClientRect();
      const maxW = Math.max(minWidth, rect.width * widthFactor);
      const maxH = Math.max(minHeight, Math.min(rect.height, window.innerHeight * heightFactor));

      let w = maxW;
      let h = w / aspectRatio;
      if (h > maxH) {
        h = maxH;
        w = h * aspectRatio;
      }

      setSize({ width: Math.floor(w), height: Math.floor(h) });
    };

    calc();
    const ro = new ResizeObserver(calc);
    ro.observe(node);
    window.addEventListener('resize', calc);
    return () => {
      ro.disconnect();
      window.removeEventListener('resize', calc);
    };
  }, [el, opts?.widthFactor, opts?.heightFactor, opts?.minWidth, opts?.minHeight, opts?.aspectRatio]);

  return size;
};

