import React, { useEffect, useRef } from 'react';

type Particle = {
  x: number;
  y: number;
  radius: number;
  vx: number;
  vy: number;
  opacity: number;
  opacitySpeed: number;
  color: string;
};

const COLORS = [
  'rgba(0, 180, 200, 0.15)',
  'rgba(100, 180, 240, 0.12)',
  'rgba(150, 220, 230, 0.10)',
];

export const GlobalMistCanvas: React.FC = () => {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const rafRef = useRef<number | null>(null);
  const particlesRef = useRef<Particle[]>([]);
  const sizeRef = useRef<{ width: number; height: number; dpr: number }>({
    width: 0,
    height: 0,
    dpr: 1,
  });

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const reduceMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches;
    const count = 38;

    const createParticles = () => {
      const { width, height } = sizeRef.current;
      const next: Particle[] = [];
      for (let i = 0; i < count; i++) {
        const radius = Math.random() * 260 + 160;
        next.push({
          x: Math.random() * width,
          y: Math.random() * height,
          radius,
          color: COLORS[Math.floor(Math.random() * COLORS.length)],
          vx: (Math.random() - 0.5) * 1.6,
          vy: (Math.random() - 0.5) * 1.1,
          opacity: Math.random() * 0.35 + 0.10,
          opacitySpeed: 0.0018 + Math.random() * 0.0028,
        });
      }
      particlesRef.current = next;
    };

    const resize = () => {
      const width = window.innerWidth;
      const height = window.innerHeight;
      const dpr = Math.min(2, Math.max(1, window.devicePixelRatio || 1));
      sizeRef.current = { width, height, dpr };
      canvas.width = Math.floor(width * dpr);
      canvas.height = Math.floor(height * dpr);
      canvas.style.width = `${width}px`;
      canvas.style.height = `${height}px`;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      createParticles();
    };

    const drawParticle = (p: Particle) => {
      const g = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, p.radius);
      g.addColorStop(0, p.color);
      g.addColorStop(1, 'rgba(255, 255, 255, 0)');
      ctx.beginPath();
      ctx.fillStyle = g;
      ctx.globalAlpha = p.opacity;
      ctx.arc(p.x, p.y, p.radius, 0, Math.PI * 2);
      ctx.fill();
    };

    const updateParticle = (p: Particle) => {
      const { width, height } = sizeRef.current;
      p.x += p.vx;
      p.y += p.vy;

      p.opacity += p.opacitySpeed;
      if (p.opacity > 0.62 || p.opacity < 0.08) {
        p.opacitySpeed *= -1;
      }

      if (p.x < -p.radius) p.x = width + p.radius;
      if (p.x > width + p.radius) p.x = -p.radius;
      if (p.y < -p.radius) p.y = height + p.radius;
      if (p.y > height + p.radius) p.y = -p.radius;
    };

    const frame = () => {
      const { width, height } = sizeRef.current;
      ctx.clearRect(0, 0, width, height);
      const particles = particlesRef.current;
      for (let i = 0; i < particles.length; i++) {
        if (!reduceMotion) updateParticle(particles[i]);
        drawParticle(particles[i]);
      }
      rafRef.current = window.requestAnimationFrame(frame);
    };

    resize();
    rafRef.current = window.requestAnimationFrame(frame);
    window.addEventListener('resize', resize, { passive: true });

    return () => {
      window.removeEventListener('resize', resize);
      if (rafRef.current != null) {
        window.cancelAnimationFrame(rafRef.current);
        rafRef.current = null;
      }
    };
  }, []);

  return <canvas id="smoke-canvas" ref={canvasRef} aria-hidden="true" />;
};

