import React, { useEffect, useMemo, useRef, useState } from 'react';
import { FileText, FolderArchive, Presentation, MessageSquareText, Code, Headphones, Pause, Play, Download, X, BarChart3, HelpCircle, RefreshCw } from 'lucide-react';
import clsx from 'clsx';
import { StageNav } from '../StageNav';
import { useProjectStore } from '../../store/useProjectStore';
import { getHtmlPages, getPreviewCoach, getPreviewMetrics, getPreviewQuestions, getPreviewInsightsBundle, regeneratePreviewCoach, regeneratePreviewQuestions } from '../../api/projects';
import { AutoFitIframe } from '../AutoFitIframe';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { useStageCanvasSize } from '../../hooks/useStageCanvasSize';

type ExportKind = 'pdf' | 'pptx' | 'speech' | 'html' | 'images' | 'project';

const apiBase = () => {
  const apiOrigin = String(import.meta.env.VITE_API_URL || '').replace(/\/+$/, '');
  return apiOrigin ? `${apiOrigin}/api/v1` : '/api/v1';
};

const exportUrl = (projectId: string, kind: ExportKind, mode?: string) => {
  if (kind === 'pdf') return `${apiBase()}/projects/${projectId}/export/pdf`;
  if (kind === 'pptx') {
    const m = String(mode || '').trim();
    const qs = m ? `?mode=${encodeURIComponent(m)}` : '';
    return `${apiBase()}/projects/${projectId}/export/pptx${qs}`;
  }
  if (kind === 'speech') return `${apiBase()}/projects/${projectId}/export/speech.txt`;
  if (kind === 'html') return `${apiBase()}/projects/${projectId}/export/html.zip`;
  if (kind === 'images') return `${apiBase()}/projects/${projectId}/export/images.zip`;
  return `${apiBase()}/projects/${projectId}/export/project.zip`;
};

const modeLabel = (m: string) => {
  if (m === 'dynamic_prepend') return 'Dynamic v1: HTML before PDF';
  if (m === 'dynamic_append') return 'Dynamic v2: HTML after PDF';
  if (m === 'dynamic_replace') return 'Dynamic v3: Replace PDF with HTML';
  return 'Static (PDF)';
};

const modeShortLabel = (m: string) => {
  if (m === 'dynamic_prepend') return 'Dynamic v1';
  if (m === 'dynamic_append') return 'Dynamic v2';
  if (m === 'dynamic_replace') return 'Dynamic v3';
  return 'Static';
};

const PreviewView: React.FC = () => {
  const {
    currentProject,
    previewImages,
    currentPage,
    setPage,
    exportMode,
    autoTtsBeforePreview,
    setBusyLabel,
    loadEditorFiles,
    editorFiles,
  } = useProjectStore();

  const [exporting, setExporting] = useState<ExportKind | null>(null);
  const [exportMenuOpen, setExportMenuOpen] = useState(false);
  const [audioBusy, setAudioBusy] = useState(false);
  const [isPlaying, setIsPlaying] = useState(false);
  const [metricsOpen, setMetricsOpen] = useState(false);
  const [questionsOpen, setQuestionsOpen] = useState(false);
  const [previewMetrics, setPreviewMetrics] = useState<any | null>(null);
  const [metricsLoading, setMetricsLoading] = useState(false);
  const [metricsError, setMetricsError] = useState<string | null>(null);
  const [coachStateByPage, setCoachStateByPage] = useState<Record<number, { loading: boolean; loaded: boolean; advice: string[]; error?: string }>>({});
  const [questionsStateByPage, setQuestionsStateByPage] = useState<Record<number, { loading: boolean; loaded: boolean; questions: string[]; error?: string }>>({});
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const previewBoundsRef = useRef<HTMLDivElement | null>(null);
  const stageCanvasSize = useStageCanvasSize(previewBoundsRef);

  useEffect(() => {
    if (!currentProject) return;
    loadEditorFiles();
  }, [currentProject?.project_id]);

  const [htmlMeta, setHtmlMeta] = useState<{ pages: string[]; meta?: any } | null>(null);

  useEffect(() => {
    if (!currentProject) return;
    if (exportMode === 'static') {
      setHtmlMeta(null);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const r = await getHtmlPages(currentProject.project_id);
        if (!cancelled) setHtmlMeta(r);
      } catch {
        if (!cancelled) setHtmlMeta({ pages: [] });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [currentProject?.project_id, exportMode]);

  const htmlPageMap = useMemo(() => {
    const map = new Map<number, string>();
    const pages = htmlMeta?.pages || [];
    for (const fn of pages) {
      const m = String(fn).match(/slide_(\d+)\.html/i);
      if (!m) continue;
      const idx = Number(m[1]) - 1;
      if (Number.isFinite(idx) && idx >= 0) map.set(idx, fn);
    }
    return map;
  }, [htmlMeta?.pages]);

  type PreviewItem = { kind: 'beamer' | 'html'; pageIndex: number; htmlFile?: string; beamerFile?: string };
  const previewItems = useMemo<PreviewItem[]>(() => {
    const beamer = previewImages.map((fn, i) => ({ kind: 'beamer' as const, pageIndex: i, beamerFile: fn }));
    if (exportMode === 'static') return beamer;

    const hasHtml = (i: number) => htmlPageMap.has(i);
    const htmlItem = (i: number): PreviewItem => ({ kind: 'html', pageIndex: i, htmlFile: htmlPageMap.get(i) || undefined });

    if (exportMode === 'dynamic_replace') {
      return beamer.map((it) => (hasHtml(it.pageIndex) ? htmlItem(it.pageIndex) : it));
    }

    if (exportMode === 'dynamic_prepend') {
      const out: PreviewItem[] = [];
      for (const it of beamer) {
        if (hasHtml(it.pageIndex)) out.push(htmlItem(it.pageIndex));
        out.push(it);
      }
      return out;
    }

    const out: PreviewItem[] = [];
    for (const it of beamer) {
      out.push(it);
      if (hasHtml(it.pageIndex)) out.push(htmlItem(it.pageIndex));
    }
    return out;
  }, [exportMode, previewImages, htmlPageMap]);

  useEffect(() => {
    if (currentPage < previewItems.length) return;
    setPage(Math.max(0, previewItems.length - 1));
  }, [currentPage, previewItems.length]);

  const currentItem = previewItems[currentPage] || null;
  const speechSegments = useMemo(() => {
    const raw = String(editorFiles?.speech || '').trim();
    if (!raw) return [] as string[];
    return raw.split('<next>').map((s) => s.trim());
  }, [editorFiles?.speech]);

  const currentSpeech = useMemo(() => {
    if (!currentItem) return '';
    return speechSegments[currentItem.pageIndex] || '';
  }, [speechSegments, currentItem?.pageIndex]);
  const previewSrc = useMemo(() => {
    if (!currentProject || !currentItem) return null;
    if (currentItem.kind === 'html' && currentItem.htmlFile) {
      return `${apiBase()}/projects/${currentProject.project_id}/html/${currentItem.htmlFile}?t=${Date.now()}`;
    }
    if (currentItem.kind === 'beamer' && currentItem.beamerFile) {
      return `${apiBase()}/projects/${currentProject.project_id}/preview/${currentItem.beamerFile}?t=${Date.now()}`;
    }
    return null;
  }, [currentProject, currentItem?.kind, currentItem?.htmlFile, currentItem?.beamerFile]);

  const doExport = async (kind: ExportKind) => {
    if (!currentProject) return;
    setExporting(kind);
    try {
      setBusyLabel(
        kind === 'pdf'
          ? 'Preparing PDF export…'
          : kind === 'pptx'
            ? 'Preparing PPTX export…'
            : kind === 'speech'
              ? 'Preparing speech export…'
              : kind === 'html'
                ? 'Preparing HTML export…'
                : kind === 'images'
                  ? 'Preparing images export…'
                  : 'Preparing project export…'
      );
      window.open(
        exportUrl(currentProject.project_id, kind, kind === 'pptx' ? exportMode : undefined),
        '_blank',
        'noopener,noreferrer'
      );
    } finally {
      setTimeout(() => {
        setExporting(null);
        setBusyLabel(null);
      }, 600);
    }
  };

  if (!currentProject) return null;

  const audioUrlFor = (pageIndex: number) => `${apiBase()}/projects/${currentProject.project_id}/tts/${pageIndex}?t=${Date.now()}`;

  const ensureAndPlay = async () => {
    if (!currentProject || !currentItem) return;
    const pageIndex = currentItem.pageIndex;
    setAudioBusy(true);
    try {
      const url = audioUrlFor(pageIndex);
      if (!audioRef.current) {
        audioRef.current = new Audio(url);
        audioRef.current.addEventListener('ended', () => setIsPlaying(false));
      } else {
        audioRef.current.src = url;
      }
      await audioRef.current.play();
      setIsPlaying(true);
    } catch {
      setIsPlaying(false);
      setBusyLabel('Audio not ready. Enable TTS before Preview and re-enter Preview.');
      setTimeout(() => setBusyLabel(null), 1500);
    } finally {
      setAudioBusy(false);
    }
  };

  const togglePlay = async () => {
    if (!audioRef.current || !isPlaying) {
      await ensureAndPlay();
      return;
    }
    audioRef.current.pause();
    setIsPlaying(false);
  };

  useEffect(() => {
    if (!exportMenuOpen) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setExportMenuOpen(false);
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [exportMenuOpen]);

  useEffect(() => {
    if (!metricsOpen && !questionsOpen) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setMetricsOpen(false);
        setQuestionsOpen(false);
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [metricsOpen, questionsOpen]);

  useEffect(() => {
    if (!currentProject) return;
    if (!metricsOpen && !questionsOpen) return;
    if (previewMetrics || metricsLoading) return;
    let cancelled = false;
    setMetricsLoading(true);
    setMetricsError(null);
    (async () => {
      try {
        const r = await getPreviewMetrics(currentProject.project_id);
        if (!cancelled) setPreviewMetrics(r);
      } catch (e: any) {
        const msg = String(e?.response?.data?.detail || e?.message || 'Failed to load metrics');
        if (!cancelled) setMetricsError(msg);
      } finally {
        if (!cancelled) setMetricsLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [currentProject?.project_id, metricsOpen, questionsOpen, previewMetrics, metricsLoading]);

  const currentBasePageIndex = currentItem?.pageIndex ?? null;

  useEffect(() => {
    if (!currentProject?.project_id) return;
    if (previewMetrics) return;
    let cancelled = false;
    (async () => {
      try {
        const r = await getPreviewInsightsBundle(currentProject.project_id);
        if (cancelled) return;
        if (r?.metrics?.ok) setPreviewMetrics(r.metrics);
        const coachByPage = r?.coach?.by_page || {};
        const coachErr = r?.coach?.errors_by_page || {};
        const qByPage = r?.questions?.by_page || {};
        const qErr = r?.questions?.errors_by_page || {};

        setCoachStateByPage((s) => {
          const next = { ...s };
          Object.keys(coachByPage).forEach((k) => {
            const idx = Number(k);
            if (!Number.isFinite(idx)) return;
            if (next[idx]?.loaded) return;
            next[idx] = { loading: false, loaded: true, advice: coachByPage[k] || [], error: coachErr[k] || undefined };
          });
          return next;
        });
        setQuestionsStateByPage((s) => {
          const next = { ...s };
          Object.keys(qByPage).forEach((k) => {
            const idx = Number(k);
            if (!Number.isFinite(idx)) return;
            if (next[idx]?.loaded) return;
            next[idx] = { loading: false, loaded: true, questions: qByPage[k] || [], error: qErr[k] || undefined };
          });
          return next;
        });
      } catch {
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [currentProject?.project_id, previewMetrics]);

  useEffect(() => {
    if (!currentProject) return;
    if (!metricsOpen) return;
    if (currentBasePageIndex === null) return;
    if (coachStateByPage[currentBasePageIndex]?.loading) return;
    if (coachStateByPage[currentBasePageIndex]?.loaded) return;
    setCoachStateByPage((s) => ({ ...s, [currentBasePageIndex]: { loading: true, loaded: false, advice: [] } }));
    const pi = currentBasePageIndex;
    let cancelled = false;
    (async () => {
      try {
        const r = await getPreviewCoach(currentProject.project_id, currentBasePageIndex);
        if (!cancelled) setCoachStateByPage((s) => ({ ...s, [currentBasePageIndex]: { loading: false, loaded: true, advice: r.advice || [], error: r.error || undefined } }));
      } catch (e: any) {
        const msg = String(e?.response?.data?.detail || e?.message || 'Failed to generate advice');
        if (!cancelled) setCoachStateByPage((s) => ({ ...s, [currentBasePageIndex]: { loading: false, loaded: true, advice: [], error: msg } }));
      }
    })();
    return () => {
      cancelled = true;
      setCoachStateByPage((s) => {
        const cur = s[pi];
        if (!cur || !cur.loading) return s;
        return { ...s, [pi]: { ...cur, loading: false } };
      });
    };
  }, [currentProject?.project_id, metricsOpen, currentBasePageIndex]);

  useEffect(() => {
    if (!currentProject) return;
    if (!questionsOpen) return;
    if (currentBasePageIndex === null) return;
    if (questionsStateByPage[currentBasePageIndex]?.loading) return;
    if (questionsStateByPage[currentBasePageIndex]?.loaded) return;
    setQuestionsStateByPage((s) => ({ ...s, [currentBasePageIndex]: { loading: true, loaded: false, questions: [] } }));
    const pi = currentBasePageIndex;
    let cancelled = false;
    (async () => {
      try {
        const r = await getPreviewQuestions(currentProject.project_id, currentBasePageIndex);
        if (!cancelled) setQuestionsStateByPage((s) => ({ ...s, [currentBasePageIndex]: { loading: false, loaded: true, questions: r.questions || [], error: r.error || undefined } }));
      } catch (e: any) {
        const msg = String(e?.response?.data?.detail || e?.message || 'Failed to generate questions');
        if (!cancelled) setQuestionsStateByPage((s) => ({ ...s, [currentBasePageIndex]: { loading: false, loaded: true, questions: [], error: msg } }));
      }
    })();
    return () => {
      cancelled = true;
      setQuestionsStateByPage((s) => {
        const cur = s[pi];
        if (!cur || !cur.loading) return s;
        return { ...s, [pi]: { ...cur, loading: false } };
      });
    };
  }, [currentProject?.project_id, questionsOpen, currentBasePageIndex]);

  const exportItems = useMemo(() => {
    return [
      { kind: 'pdf' as const, label: 'PDF', icon: FileText, primary: false },
      { kind: 'pptx' as const, label: 'PPTX', icon: Presentation, primary: false },
      { kind: 'html' as const, label: 'HTML', icon: Code, primary: false },
      { kind: 'project' as const, label: 'Project', icon: FolderArchive, primary: false },
      { kind: 'speech' as const, label: 'Speech', icon: MessageSquareText, primary: false },
    ];
  }, []);


  const fanPositions = useMemo(() => {
    const radius = 130;
    const angles = exportItems.map((_, i) => {
      if (exportItems.length <= 1) return -135;
      const start = -180;
      const end = -90;
      const step = (end - start) / (exportItems.length - 1);
      return start + step * i;
    });
    return angles.map((deg) => {
      const rad = (deg * Math.PI) / 180;
      return { x: Math.cos(rad) * radius, y: Math.sin(rad) * radius };
    });
  }, [exportItems]);

  const scoreColor = (v: number) => {
    if (v >= 0.7) return 'from-emerald-500 to-teal-500';
    if (v >= 0.45) return 'from-amber-500 to-orange-500';
    return 'from-rose-500 to-pink-500';
  };

  const scoreText = (v: number) => `${Math.round(Math.max(0, Math.min(1, v)) * 100)}%`;

  const currentSlideMetrics = useMemo(() => {
    if (!previewMetrics?.ok) return null;
    if (currentBasePageIndex === null) return null;
    const items = Array.isArray(previewMetrics?.per_slide) ? previewMetrics.per_slide : [];
    return items.find((it: any) => Number(it?.page_index) === Number(currentBasePageIndex)) || null;
  }, [previewMetrics, currentBasePageIndex]);

  const metricDefs = useMemo(() => {
    return [
      { key: 'legibility', label: 'Legibility' },
      { key: 'time_pace', label: 'Time Pacing' },
      { key: 'transition', label: 'Transition Flow' },
      { key: 'script_complement', label: 'Script Complement' },
      { key: 'focus_readiness', label: 'Visual Focus' },
    ] as const;
  }, []);

  const anyPanelOpen = metricsOpen || questionsOpen;

  return (
    <div className="h-screen bg-transparent flex flex-col">
      <StageNav 
        rightContent={
          <div className="flex flex-col items-end min-w-0 text-right">
              <div className="text-xs font-bold text-slate-900 flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse"></span>
                Preview & Export ({modeShortLabel(exportMode)})
              </div>
              <div className="text-[10px] text-slate-500 font-medium mt-0.5">{modeLabel(exportMode)}</div>
          </div>
        }
      />

      <div className="flex-1 flex flex-col relative z-10 px-4 pb-0 pt-4 gap-4">
        <div ref={previewBoundsRef} className="flex-1 relative flex items-center justify-center min-h-0">
          <div className="relative w-full h-full flex flex-col items-center justify-center">
            <div
              className={clsx(
                'relative transition-all duration-500 group hover:-translate-y-2 hover:shadow-[0_30px_60px_-15px_rgba(0,0,0,0.15)]',
                'mx-auto my-auto'
              )}
              style={stageCanvasSize ? { width: stageCanvasSize.width, height: stageCanvasSize.height } : undefined}
            >
              <div className="w-full h-full bg-white rounded-xl shadow-[0_20px_50px_-12px_rgba(0,0,0,0.1)] border border-slate-200/60 overflow-hidden relative transition-all">
                {previewSrc ? (
                  currentItem?.kind === 'html' ? (
                    <AutoFitIframe src={previewSrc} className="w-full h-full" title="HTML Preview" />
                  ) : (
                    <img src={previewSrc} alt="Preview" className="w-full h-full object-contain bg-white" />
                  )
                ) : (
                  <div className="w-full h-full flex items-center justify-center text-slate-400 bg-slate-50">
                    <div className="text-center">
                      <div className="text-sm font-medium">No Preview Available</div>
                    </div>
                  </div>
                )}

                {currentSpeech ? (
                  <div className="absolute left-0 top-0 bottom-0 pointer-events-none">
                    <div className="h-full w-[360px] p-3">
                      <div className="h-full -translate-x-4 opacity-0 group-hover:translate-x-0 group-hover:opacity-100 transition-transform transition-opacity duration-200 transform-gpu will-change-transform will-change-opacity rounded-2xl bg-gradient-to-br from-cyan-400/70 via-teal-400/55 to-blue-500/70 p-[1px] shadow-lg shadow-cyan-200/25">
                        <div className="h-full rounded-2xl bg-white/90 backdrop-blur-xl border border-white/30 px-4 py-4 text-[13px] leading-relaxed text-slate-700 overflow-y-auto">
                          <div className="whitespace-pre-wrap">{currentSpeech}</div>
                        </div>
                      </div>
                    </div>
                  </div>
                ) : null}
              </div>

              <div className="absolute bottom-6 left-1/2 -translate-x-1/2 bg-white/90 px-1.5 py-1.5 rounded-full shadow-lg border border-white/50 flex items-center gap-3 text-sm font-medium text-slate-600 opacity-0 group-hover:opacity-100 transition-all duration-300 transform translate-y-2 group-hover:translate-y-0">
                <button
                  className="hover:bg-slate-100 w-8 h-8 rounded-full flex items-center justify-center transition-colors disabled:opacity-30"
                  onClick={() => setPage(Math.max(0, currentPage - 1))}
                  disabled={currentPage <= 0}
                >
                  <ChevronLeft size={16} />
                </button>
                <span className="min-w-[80px] text-center font-bold text-slate-700 text-xs">
                  {previewItems.length ? currentPage + 1 : 0} / {previewItems.length || 0}
                </span>
                <button
                  className="hover:bg-slate-100 w-8 h-8 rounded-full flex items-center justify-center transition-colors disabled:opacity-30"
                  onClick={() => setPage(currentPage + 1)}
                  disabled={previewItems.length === 0 || currentPage >= previewItems.length - 1}
                >
                  <ChevronRight size={16} />
                </button>
                 <button
                  type="button"
                  onClick={togglePlay}
                  disabled={audioBusy || !currentItem || !autoTtsBeforePreview}
                  className={clsx(
                    'hover:bg-slate-100 w-8 h-8 rounded-full flex items-center justify-center transition-colors disabled:opacity-30',
                    (audioBusy || !currentItem || !autoTtsBeforePreview) && 'cursor-not-allowed'
                  )}
                  title={autoTtsBeforePreview ? 'Play voice' : 'TTS before Preview is disabled'}
                >
                  {audioBusy ? <Headphones className="h-4 w-4 animate-pulse" /> : isPlaying ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>

      {anyPanelOpen && (
        <button
          type="button"
          className="fixed inset-0 z-[80] bg-slate-900/10"
          onClick={() => {
            setMetricsOpen(false);
            setQuestionsOpen(false);
          }}
          aria-label="Close preview panels"
        />
      )}

      <div className="fixed left-6 bottom-6 z-[95] flex items-end gap-3">
        <button
          type="button"
          onClick={() => {
            setQuestionsOpen(false);
            setMetricsOpen((v) => !v);
          }}
          className={clsx(
            'h-14 w-14 rounded-full shadow-xl border flex items-center justify-center transition-colors',
            metricsOpen ? 'bg-white border-slate-200 text-slate-700 hover:bg-slate-50' : 'bg-teal-600 border-teal-600 text-white hover:bg-teal-700'
          )}
          title="Data Panel"
        >
          <BarChart3 className="h-6 w-6" />
        </button>

        <button
          type="button"
          onClick={() => {
            setMetricsOpen(false);
            setQuestionsOpen((v) => !v);
          }}
          className={clsx(
            'h-14 w-14 rounded-full shadow-xl border flex items-center justify-center transition-colors',
            questionsOpen ? 'bg-white border-slate-200 text-slate-700 hover:bg-slate-50' : 'bg-teal-600 border-teal-600 text-white hover:bg-teal-700'
          )}
          title="Audience Q&A"
        >
          <HelpCircle className="h-6 w-6" />
        </button>
      </div>

      {metricsOpen && (
        <div className="fixed left-6 bottom-[92px] z-[95] w-[380px] max-w-[calc(100vw-48px)] max-h-[70vh]">
          <div className="rounded-2xl bg-gradient-to-br from-cyan-400/70 via-teal-400/55 to-blue-500/70 p-[1px] shadow-lg shadow-cyan-200/25">
            <div className="rounded-2xl bg-white/90 backdrop-blur-xl border border-white/30 px-4 py-4 overflow-hidden">
              <div className="flex items-center justify-between gap-3">
                <div className="min-w-0">
                  <div className="text-xs font-bold text-slate-900">Data Panel</div>
                  <div className="text-[10px] text-slate-500 font-medium mt-0.5">Slide metrics and rehearsal tips</div>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    className="h-8 w-8 rounded-full hover:bg-slate-100 flex items-center justify-center text-slate-600"
                    onClick={() => {
                      if (currentBasePageIndex === null || !currentProject) return;
                      setCoachStateByPage((s) => ({ ...s, [currentBasePageIndex]: { loading: true, loaded: false, advice: [] } }));
                      void (async () => {
                        try {
                          const r = await regeneratePreviewCoach(currentProject.project_id, currentBasePageIndex);
                          setCoachStateByPage((s) => ({ ...s, [currentBasePageIndex]: { loading: false, loaded: true, advice: r.advice || [] } }));
                        } catch (e: any) {
                          const msg = String(e?.response?.data?.detail || e?.message || 'Failed to generate advice');
                          setCoachStateByPage((s) => ({ ...s, [currentBasePageIndex]: { loading: false, loaded: true, advice: [], error: msg } }));
                        }
                      })();
                    }}
                    title="Refresh tips"
                  >
                    <RefreshCw className={clsx('h-4 w-4', coachStateByPage[currentBasePageIndex ?? -1]?.loading && 'animate-spin')} />
                  </button>
                  <button
                    type="button"
                    className="h-8 w-8 rounded-full hover:bg-slate-100 flex items-center justify-center text-slate-600"
                    onClick={() => setMetricsOpen(false)}
                    title="Close"
                  >
                    <X className="h-4 w-4" />
                  </button>
                </div>
              </div>

              <div className="mt-4 space-y-3">
                {metricsLoading ? (
                  <div className="text-xs text-slate-500">Computing metrics…</div>
                ) : metricsError ? (
                  <div className="text-xs text-rose-600 break-words">{metricsError}</div>
                ) : !currentSlideMetrics ? (
                  <div className="text-xs text-slate-500">No metrics available</div>
                ) : (
                  <>
                    {metricDefs.map((d) => {
                      const v = Number(currentSlideMetrics?.metrics?.[d.key] ?? 0);
                      return (
                        <div key={d.key} className="flex items-center gap-3">
                          <div className="w-16 text-[11px] font-semibold text-slate-700">{d.label}</div>
                          <div className="flex-1 h-2.5 rounded-full bg-slate-100 overflow-hidden border border-slate-200/60">
                            <div className={clsx('h-full rounded-full bg-gradient-to-r', scoreColor(v))} style={{ width: `${Math.round(Math.max(0, Math.min(1, v)) * 100)}%` }} />
                          </div>
                          <div className="w-10 text-right text-[11px] font-bold text-slate-700 tabular-nums">{scoreText(v)}</div>
                        </div>
                      );
                    })}
                    <div className="pt-2 border-t border-slate-200/70">
                      <div className="text-[11px] font-bold text-slate-800 mb-2">Tips</div>
                      {currentBasePageIndex !== null && coachStateByPage[currentBasePageIndex]?.error ? (
                        <div className="text-xs text-rose-600 break-words">{coachStateByPage[currentBasePageIndex].error}</div>
                      ) : currentBasePageIndex !== null && coachStateByPage[currentBasePageIndex]?.loading ? (
                        <div className="text-xs text-slate-500">Generating…</div>
                      ) : currentBasePageIndex !== null && coachStateByPage[currentBasePageIndex]?.advice?.length ? (
                        <div className="space-y-1.5">
                          {coachStateByPage[currentBasePageIndex].advice.slice(0, 6).map((t, idx) => (
                            <div key={idx} className="text-[12px] leading-relaxed text-slate-700">
                              {idx + 1}. {t}
                            </div>
                          ))}
                        </div>
                      ) : (
                        <div className="text-xs text-slate-500">No tips (PREVIEW_COACH not configured)</div>
                      )}
                    </div>
                  </>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {questionsOpen && (
        <div className="fixed left-6 bottom-[92px] z-[95] w-[380px] max-w-[calc(100vw-48px)] max-h-[70vh]">
          <div className="rounded-2xl bg-gradient-to-br from-cyan-400/70 via-teal-400/55 to-blue-500/70 p-[1px] shadow-lg shadow-cyan-200/25">
            <div className="rounded-2xl bg-white/90 backdrop-blur-xl border border-white/30 px-4 py-4 overflow-hidden">
              <div className="flex items-center justify-between gap-3">
                <div className="min-w-0">
                  <div className="text-xs font-bold text-slate-900">Audience Q&A</div>
                  <div className="text-[10px] text-slate-500 font-medium mt-0.5">Most likely audience questions for this slide</div>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    className="h-8 w-8 rounded-full hover:bg-slate-100 flex items-center justify-center text-slate-600"
                    onClick={() => {
                      if (currentBasePageIndex === null || !currentProject) return;
                      setQuestionsStateByPage((s) => ({ ...s, [currentBasePageIndex]: { loading: true, loaded: false, questions: [] } }));
                      void (async () => {
                        try {
                          const r = await regeneratePreviewQuestions(currentProject.project_id, currentBasePageIndex);
                          setQuestionsStateByPage((s) => ({ ...s, [currentBasePageIndex]: { loading: false, loaded: true, questions: r.questions || [] } }));
                        } catch (e: any) {
                          const msg = String(e?.response?.data?.detail || e?.message || 'Failed to generate questions');
                          setQuestionsStateByPage((s) => ({ ...s, [currentBasePageIndex]: { loading: false, loaded: true, questions: [], error: msg } }));
                        }
                      })();
                    }}
                    title="Refresh questions"
                  >
                    <RefreshCw className={clsx('h-4 w-4', questionsStateByPage[currentBasePageIndex ?? -1]?.loading && 'animate-spin')} />
                  </button>
                  <button
                    type="button"
                    className="h-8 w-8 rounded-full hover:bg-slate-100 flex items-center justify-center text-slate-600"
                    onClick={() => setQuestionsOpen(false)}
                    title="Close"
                  >
                    <X className="h-4 w-4" />
                  </button>
                </div>
              </div>

              <div className="mt-4">
                {metricsLoading ? (
                  <div className="text-xs text-slate-500">Loading…</div>
                ) : metricsError ? (
                  <div className="text-xs text-rose-600 break-words">{metricsError}</div>
                ) : currentBasePageIndex !== null && questionsStateByPage[currentBasePageIndex]?.error ? (
                  <div className="text-xs text-rose-600 break-words">{questionsStateByPage[currentBasePageIndex].error}</div>
                ) : currentBasePageIndex !== null && questionsStateByPage[currentBasePageIndex]?.loading ? (
                  <div className="text-xs text-slate-500">Generating…</div>
                ) : currentBasePageIndex !== null && questionsStateByPage[currentBasePageIndex]?.questions?.length ? (
                  <div className="space-y-2">
                    {questionsStateByPage[currentBasePageIndex].questions.slice(0, 3).map((q, idx) => (
                      <div key={idx} className="text-[12px] leading-relaxed text-slate-700">
                        Q{idx + 1}. {q}
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="text-xs text-slate-500">No questions (AUDIENCE_QA not configured)</div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {exportMenuOpen && (
        <button
          type="button"
          className="fixed inset-0 z-[90] bg-slate-900/10"
          onClick={() => setExportMenuOpen(false)}
          aria-label="Close export menu"
        />
      )}

      <div className="fixed right-6 bottom-6 z-[95]">
        <div className="absolute right-0 bottom-0 pointer-events-none">
          {exportItems.map((it, i) => {
            const pos = fanPositions[i] || { x: 0, y: 0 };
            const Icon = it.icon;
            const disabled = exporting !== null || (it.kind !== 'html' && it.kind !== 'speech' && !previewImages.length);
            const delayMs = exportMenuOpen ? i * 30 : (exportItems.length - 1 - i) * 20;
            return (
              <button
                key={it.kind}
                type="button"
                title={it.label}
                onClick={() => {
                  if (disabled || !exportMenuOpen) return;
                  void doExport(it.kind);
                  setExportMenuOpen(false);
                }}
                disabled={disabled || !exportMenuOpen}
                className={clsx(
                  'pointer-events-auto absolute right-0 bottom-0 h-10 w-10 rounded-full shadow-lg border flex items-center justify-center',
                  it.primary ? 'bg-teal-600 border-teal-600 text-white hover:bg-teal-700' : 'bg-white border-slate-200 text-slate-700 hover:bg-slate-50',
                  (disabled || !exportMenuOpen) && 'opacity-50 cursor-not-allowed'
                )}
                style={{
                  transitionProperty: 'transform, opacity',
                  transitionDuration: '220ms',
                  transitionTimingFunction: 'cubic-bezier(0.2, 0.8, 0.2, 1)',
                  transitionDelay: `${delayMs}ms`,
                  opacity: exportMenuOpen ? 1 : 0,
                  transform: exportMenuOpen ? `translate(${pos.x}px, ${pos.y}px) scale(1)` : 'translate(0px, 0px) scale(0.6)',
                  pointerEvents: exportMenuOpen ? 'auto' : 'none',
                }}
              >
                <Icon className={clsx('h-4 w-4', it.primary ? 'text-white' : 'text-teal-600')} />
              </button>
            );
          })}
        </div>

        <button
          type="button"
          onClick={() => setExportMenuOpen((v) => !v)}
          className={clsx(
            'h-14 w-14 rounded-full shadow-xl border flex items-center justify-center transition-colors',
            exportMenuOpen ? 'bg-white border-slate-200 text-slate-700 hover:bg-slate-50' : 'bg-teal-600 border-teal-600 text-white hover:bg-teal-700'
          )}
          title="Download"
        >
          {exportMenuOpen ? <X className="h-6 w-6" /> : <Download className="h-6 w-6" />}
        </button>
      </div>
    </div>
  );
};

export default PreviewView;
