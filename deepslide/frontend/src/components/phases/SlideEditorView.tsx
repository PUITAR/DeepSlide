import { useMemo, useState, useEffect, useRef } from 'react';
import { 
  Mic, Monitor, ChevronLeft, ChevronRight, Edit3, Sparkles, FileText,
  RefreshCw, CheckCircle2, X, Share2, Star, StopCircle,
  Image as ImageIcon, Table2, Type, Zap, Plus, Minus
} from 'lucide-react';
import { useProjectStore } from '../../store/useProjectStore';
import { StageNav } from '../StageNav';
import { AutoFitIframe } from '../AutoFitIframe';
import SlideThemeSelector, { type SlideThemePreset } from '../SlideThemeSelector';
import { aiBeautify, aiGenerateHtml, getHtmlGenStatus, getHtmlPages, selectVoice, getProject } from '../../api/projects';
import { useAudioRecorder } from '../../hooks/useAudioRecorder';
import { transcribeAudio } from '../../api/audio';
import { generateTtsForPages } from '../../api/tts';
import { useStageCanvasSize } from '../../hooks/useStageCanvasSize';
import clsx from 'clsx';

const SlideEditorView = () => {
  const { 
    currentProject, editorFiles, activePanel, previewMode, previewImages, currentPage, 
    isCompiling, isThinking, compilerErrors,
    updateEditorFile, saveEditorState, compile, executeCommand,
    setActivePanel, setPreviewMode, setPage, loadEditorFiles,
    setExportMode, navigateTo, setBusyLabel, setBusyProgress, setCurrentProject,
    autoTtsBeforePreview, setAutoTtsBeforePreview,
    precomputeInsightsBeforePreview, setPrecomputeInsightsBeforePreview
  } = useProjectStore();

  const [editTab, setEditTab] = useState<'content' | 'speech' | 'title' | 'base'>('content');
  const [inputText, setInputText] = useState('');
  const [isExportOpen, setIsExportOpen] = useState(false);
  const [exportChoice, setExportChoice] = useState<'static' | 'dynamic_prepend' | 'dynamic_append' | 'dynamic_replace'>('static');
  const [previewBust, setPreviewBust] = useState(0);
  const [aiTab, setAiTab] = useState<'voice' | 'beautify' | 'enrich'>('voice');
  const [beautifyRounds, setBeautifyRounds] = useState(1);
  const [collectedPages, setCollectedPages] = useState<Set<number>>(new Set());
  const [enrichEffects, setEnrichEffects] = useState<string[]>(['Image Focus', 'Auto Diagram', 'Table Viz', 'Text Keynote', 'Motion', 'Auto Layout']);
  const [visualFx, setVisualFx] = useState(true);
  const [htmlPages, setHtmlPages] = useState<string[]>([]);
  const recorder = useAudioRecorder();
  const [voiceBlob, setVoiceBlob] = useState<Blob | null>(null);
  const [isCloningVoice, setIsCloningVoice] = useState(false);
  const previewBoundsRef = useRef<HTMLDivElement | null>(null);
  const stageCanvasSize = useStageCanvasSize(previewBoundsRef);
  const [htmlThemePreset, setHtmlThemePreset] = useState<SlideThemePreset>(() => {
    const saved = window.localStorage.getItem('deepslide_html_theme');
    return (saved as SlideThemePreset) || 'modern-glass';
  });

  useEffect(() => {
    window.localStorage.setItem('deepslide_html_theme', htmlThemePreset);
  }, [htmlThemePreset]);

  const currentPreviewImage = previewImages[currentPage] || null;

  useEffect(() => {
    if (recorder.lastBlob) {
      setVoiceBlob(recorder.lastBlob);
    }
  }, [recorder.lastBlob]);

  const isCollected = useMemo(() => collectedPages.has(currentPage), [collectedPages, currentPage]);

  
  useEffect(() => {
    loadEditorFiles();
  }, [currentProject]);
  const speechSegments = useMemo(() => {
    const raw = String(editorFiles?.speech || '');
    if (!raw.trim()) return [] as string[];
    return raw.split('<next>').map((s) => s.trim());
  }, [editorFiles?.speech]);

  const currentHtmlFile = useMemo(() => {
    if (previewMode !== 'html') return null;
    return htmlPages[currentPage] || null;
  }, [previewMode, htmlPages, currentPage]);

  const currentSpeech = useMemo(() => {
    if (!speechSegments.length) return '';
    let speechPageIndex = currentPage;
    if (previewMode === 'html') {
      const fn = String(currentHtmlFile || '');
      const m = fn.match(/slide_(\d+)\.html/i);
      if (m) {
        const idx = Number(m[1]) - 1;
        if (Number.isFinite(idx) && idx >= 0) speechPageIndex = idx;
      }
    }
    return speechSegments[speechPageIndex] || '';
  }, [speechSegments, currentPage, previewMode, currentHtmlFile]);

  const renderedSpeech = useMemo(() => {
    const s = String(currentSpeech || '').trimEnd();
    if (!s) return null;
    return (
      <div className="whitespace-pre-wrap">
        {s}
      </div>
    );
  }, [currentSpeech]);

  useEffect(() => {
    queueMicrotask(() => setPreviewBust(Date.now()));
  }, [currentProject?.project_id, currentPage, currentPreviewImage]);

  const handleUpdate = async () => {
    await saveEditorState();
    await compile();
    setPreviewBust(Date.now());
  };

  const handleCommand = async () => {
    if (!inputText.trim()) return;
    await executeCommand(inputText);
    setInputText('');
    setPreviewBust(Date.now());
  };

  const apiOrigin = String(import.meta.env.VITE_API_URL || '').replace(/\/+$/, '');
  const apiBase = apiOrigin ? `${apiOrigin}/api/v1` : '/api/v1';

  const editorTabs = ['content', 'speech', 'title', 'base'] as const;

  const voiceOptions = useMemo(() => {
    const opts: Array<{ label: string; path: string }> = [{ label: 'Default Voice', path: 'examples/voice_03.wav' }];
    if (currentProject?.voice_prompt_path) {
      opts.push({ label: 'Cloned Voice', path: currentProject.voice_prompt_path });
    }
    return opts;
  }, [currentProject?.voice_prompt_path]);

  const selectedVoicePath = currentProject?.selected_voice_path || voiceOptions[0]?.path;

  const toggleCollectCurrent = () => {
    setCollectedPages((prev) => {
      const next = new Set(prev);
      if (next.has(currentPage)) next.delete(currentPage);
      else next.add(currentPage);
      return next;
    });
  };

  const toggleCollectAll = () => {
    setCollectedPages((prev) => {
      const allSelected = previewImages.length > 0 && prev.size === previewImages.length;
      if (allSelected) return new Set();
      return new Set(previewImages.map((_, idx) => idx));
    });
  };

  const allCollected = useMemo(
    () => previewImages.length > 0 && collectedPages.size === previewImages.length,
    [collectedPages.size, previewImages.length]
  );

  const runBeautify = async () => {
    if (!currentProject) return;
    setBusyLabel('Beautifying…');
    try {
      const res = await aiBeautify(currentProject.project_id, beautifyRounds);
      if (!res.success) {
        alert('Beautify failed');
      }
      await loadEditorFiles();
    } finally {
      setBusyLabel(null);
    }
  };

  const runHtmlGenerate = async () => {
    if (!currentProject) return;
    const safePage = Math.max(0, Math.min(currentPage, Math.max(0, previewImages.length - 1)));
    const focus = collectedPages.size ? Array.from(collectedPages).sort((a, b) => a - b) : [safePage];
    setBusyLabel(`HTML: 0/${focus.length || 1}`);
    setBusyProgress(0);
    try {
      const res = await aiGenerateHtml(currentProject.project_id, focus, enrichEffects, 3, 'replace', undefined, undefined, visualFx);
      if (!res.success) {
        alert('HTML generation failed');
        return;
      }

      // Poll for status
      const sleep = (ms: number) => new Promise(r => setTimeout(r, ms));
      for (let i = 0; i < 1200; i++) {
        await sleep(500);
        try {
          const st = await getHtmlGenStatus(currentProject.project_id);
          if (st.status === 'done') break;
          if (st.status === 'error') {
            console.error(st.error);
            break; 
          }
          if (st.status === 'generating') {
            const total = st.total || focus.length || 1;
            const current = st.current || 0;
            setBusyLabel(`HTML: ${current}/${total}`);
            const pct = Math.max(0, Math.min(100, Math.round((current / Math.max(1, total)) * 100)));
            setBusyProgress(pct);
          }
        } catch (e) {
          console.warn(e);
        }
      }
      await sleep(200);

      const pagesRes = await getHtmlPages(currentProject.project_id);
      setHtmlPages(pagesRes.pages || []);
      setPreviewBust(Date.now());
    } catch (e) {
      console.error('[aiGenerateHtml] failed', e);
      alert(`HTML generation request failed: ${String((e as any)?.message || e)}`);
    } finally {
      setBusyLabel(null);
      setBusyProgress(null);
    }
  };

  const onGoClick: React.MouseEventHandler<HTMLButtonElement> = async (e) => {
    try {
      e.preventDefault();
      e.stopPropagation();
    } catch {}
    await runHtmlGenerate();
  };

  useEffect(() => {
    const load = async () => {
      if (!currentProject) return;
      if (previewMode !== 'html') return;
      const pagesRes = await getHtmlPages(currentProject.project_id);
      setHtmlPages(pagesRes.pages || []);
    };
    load();
  }, [currentProject?.project_id, previewMode]);

  const onSelectVoice = async (path: string) => {
    if (!currentProject) return;
    setBusyLabel('Updating voice…');
    try {
      await selectVoice(currentProject.project_id, path);
      const p = await getProject(currentProject.project_id);
      setCurrentProject(p);
    } finally {
      setBusyLabel(null);
    }
  };

  const cloneVoiceFromRecording = async () => {
    if (!currentProject || !voiceBlob) return;
    setIsCloningVoice(true);
    setBusyLabel('Cloning voice…');
    try {
      const res = await transcribeAudio(currentProject.project_id, voiceBlob, 'zh', true);
      const voicePath = res?.voice_path;
      if (voicePath) {
        await selectVoice(currentProject.project_id, voicePath);
      }
      const p = await getProject(currentProject.project_id);
      setCurrentProject(p);
    } finally {
      setIsCloningVoice(false);
      setBusyLabel(null);
    }
  };

  // Use state to prevent caching issues
  const previewSrc = currentPreviewImage 
    ? `${apiBase}/projects/${currentProject?.project_id}/preview/${currentPreviewImage}?t=${previewBust}` 
    : null;

  const pageCount = previewMode === 'html' ? htmlPages.length : previewImages.length;
  const htmlSrc = useMemo(() => {
    if (!currentProject || !currentHtmlFile) return null;
    return `${apiBase}/projects/${currentProject.project_id}/html/${currentHtmlFile}?t=${previewBust}`;
  }, [currentProject, currentHtmlFile, apiBase, previewBust]);

  useEffect(() => {
    if (pageCount > 0 && currentPage >= pageCount) {
      setPage(0);
    }
  }, [currentPage, pageCount, setPage]);

  return (
    <div className="flex flex-col h-screen bg-transparent text-slate-800 font-sans overflow-hidden relative selection:bg-teal-100 selection:text-teal-900">
      <StageNav 
        title={currentProject?.name || "Untitled Presentation"}
        rightContent={
           <div className="flex items-center gap-2">
              <div className="flex bg-slate-100/80 p-0.5 rounded-lg border border-slate-200/50">
                 <button 
                    onClick={() => setPreviewMode('beamer')}
                    className={clsx(
                      "px-2.5 py-1.5 rounded-md text-[11px] font-bold transition-all inline-flex items-center gap-1.5",
                      previewMode === 'beamer' ? 'bg-white shadow-sm text-teal-700' : 'text-slate-500 hover:text-slate-700'
                    )}
                 >
                    <FileText size={13} className={previewMode === 'beamer' ? 'text-teal-600' : 'text-slate-400'} />
                    PDF
                 </button>
                 <button 
                    onClick={() => setPreviewMode('html')}
                    className={clsx(
                      "px-2.5 py-1.5 rounded-md text-[11px] font-bold transition-all inline-flex items-center gap-1.5",
                      previewMode === 'html' ? 'bg-white shadow-sm text-teal-700' : 'text-slate-500 hover:text-slate-700'
                    )}
                 >
                    <Monitor size={13} className={previewMode === 'html' ? 'text-teal-600' : 'text-slate-400'} />
                    Web
                 </button>
              </div>
              <div className="h-4 w-px bg-slate-200 mx-1" />
              <button
                type="button"
                onClick={() => setIsExportOpen(true)}
                className="px-3 py-1.5 bg-teal-600 text-white text-xs font-bold rounded-lg shadow-sm hover:bg-teal-700 transition-transform active:scale-95 flex items-center gap-1.5"
              >
                <CheckCircle2 size={14} />
                Export
              </button>
           </div>
        }
      />
      
      {/* Main Content Area */}
      <div className="flex-1 flex flex-col relative z-10 px-4 pb-0 pt-4 gap-4">
        
        {/* Center Stage - Maximized Preview */}
        <div ref={previewBoundsRef} className="flex-1 relative flex items-center justify-center min-h-0">
           
           {/* Preview Container */}
           <div className="relative w-full h-full flex flex-col items-center justify-center">
              
              <div
                className={clsx(
                  'relative transition-all duration-500 group hover:-translate-y-2 hover:shadow-[0_30px_60px_-15px_rgba(0,0,0,0.15)]',
                  'mx-auto my-auto'
                )}
                style={stageCanvasSize ? { width: stageCanvasSize.width, height: stageCanvasSize.height } : undefined}
              >
                 {previewMode === 'beamer' && (
                   <div className="absolute bottom-3 right-3 z-30 flex flex-col gap-2 pointer-events-auto">
                     <button
                       type="button"
                       onClick={toggleCollectCurrent}
                       className={clsx(
                         "p-2.5 rounded-full shadow-lg border-2 border-white transition-all duration-300",
                         isCollected ? 'bg-yellow-400 text-white rotate-12 scale-110' : 'bg-white text-slate-300 hover:text-yellow-400'
                       )}
                       title={isCollected ? 'Remove from collection' : 'Collect slide for HTML'}
                     >
                       <Star size={18} fill={isCollected ? 'currentColor' : 'none'} />
                     </button>
                     <button
                       type="button"
                       onClick={toggleCollectAll}
                       className={clsx(
                         'p-2.5 rounded-2xl shadow-lg border-2 border-white transition-all',
                         allCollected ? 'bg-teal-600 text-white' : 'bg-white text-slate-500 hover:text-slate-900'
                       )}
                       title={allCollected ? 'Clear all collected' : 'Collect all slides'}
                     >
                       <CheckCircle2 size={18} />
                     </button>
                   </div>
                 )}
                 {/* Main Image */}
                 <div className="w-full h-full bg-white rounded-xl shadow-[0_20px_50px_-12px_rgba(0,0,0,0.1)] border border-slate-200/60 overflow-hidden relative transition-all">
                    {isCompiling && (
                      <div className="absolute inset-0 z-50 bg-white/80 flex flex-col items-center justify-center gap-3">
                        <div className="w-8 h-8 border-2 border-teal-100 border-t-teal-600 rounded-full animate-spin"/>
                        <span className="text-xs font-bold text-teal-600 animate-pulse">Compiling...</span>
                      </div>
                    )}
                    
                    {previewMode === 'html' ? (
                      htmlSrc ? (
                        <div className="relative w-full h-full">
                          <AutoFitIframe src={htmlSrc} className="w-full h-full" title="HTML Preview" themePreset={htmlThemePreset} />
                          {currentSpeech && (
                            <div className="absolute left-0 top-0 bottom-0 pointer-events-none">
                              <div className="h-full w-[360px] p-3">
                                <div className="h-full -translate-x-4 opacity-0 group-hover:translate-x-0 group-hover:opacity-100 transition-transform transition-opacity duration-200 transform-gpu will-change-transform will-change-opacity rounded-2xl bg-gradient-to-br from-cyan-400/70 via-teal-400/55 to-blue-500/70 p-[1px] shadow-lg shadow-cyan-200/25">
                                  <div className="h-full rounded-2xl bg-white/90 backdrop-blur-xl border border-white/30 px-4 py-4 text-[13px] leading-relaxed text-slate-700 overflow-y-auto">
                                    {renderedSpeech}
                                  </div>
                                </div>
                              </div>
                            </div>
                          )}
                        </div>
                      ) : (
                        <div className="w-full h-full flex items-center justify-center text-slate-400 bg-slate-50/50">
                          <div className="text-center max-w-sm">
                            <Monitor size={48} className="mx-auto mb-2 opacity-20"/>
                            <p className="text-sm font-medium">No HTML pages</p>
                            <p className="text-xs opacity-60 mt-1">Star pages in PDF mode, then generate HTML in Enrich.</p>
                          </div>
                        </div>
                      )
                    ) : (
                      previewSrc ? (
                        <div className="relative w-full h-full">
                          <img 
                            src={previewSrc} 
                            alt="Slide Preview" 
                            className="w-full h-full object-contain" 
                          />
                          {currentSpeech && (
                            <div className="absolute left-0 top-0 bottom-0 pointer-events-none">
                              <div className="h-full w-[360px] p-3">
                                <div className="h-full -translate-x-4 opacity-0 group-hover:translate-x-0 group-hover:opacity-100 transition-transform transition-opacity duration-200 transform-gpu will-change-transform will-change-opacity rounded-2xl bg-gradient-to-br from-cyan-400/70 via-teal-400/55 to-blue-500/70 p-[1px] shadow-lg shadow-cyan-200/25">
                                  <div className="h-full rounded-2xl bg-white/90 backdrop-blur-xl border border-white/30 px-4 py-4 text-[13px] leading-relaxed text-slate-700 overflow-y-auto">
                                    {renderedSpeech}
                                  </div>
                                </div>
                              </div>
                            </div>
                          )}
                        </div>
                      ) : (
                        <div className="w-full h-full flex items-center justify-center text-slate-400 bg-slate-50">
                           <div className="text-center">
                              <ImageIcon size={48} className="mx-auto mb-2 opacity-20"/>
                              <p className="text-sm font-medium">No Preview Available</p>
                              {compilerErrors?.length ? (
                                <div className="mt-3 mx-auto max-w-[520px] rounded-xl border border-rose-100 bg-rose-50/60 px-4 py-3 text-left">
                                  <div className="text-xs font-semibold text-rose-700">Compilation Failed</div>
                                  <div className="mt-1 text-[11px] leading-relaxed text-rose-700/90">
                                    {String(compilerErrors[0]?.message || 'Unknown error')}
                                  </div>
                                </div>
                              ) : null}
                           </div>
                        </div>
                      )
                    )}
                 </div>

                 {/* Floating Paginator (Overlay at bottom center of preview) */}
                 <div className="absolute bottom-6 left-1/2 -translate-x-1/2 bg-white/90 px-1.5 py-1.5 rounded-full shadow-lg border border-white/50 flex items-center gap-3 text-sm font-medium text-slate-600 opacity-0 group-hover:opacity-100 transition-all duration-300 transform translate-y-2 group-hover:translate-y-0">
                    <button 
                      className="hover:bg-slate-100 w-8 h-8 rounded-full flex items-center justify-center transition-colors disabled:opacity-30" 
                      onClick={() => setPage(Math.max(0, currentPage - 1))}
                      disabled={currentPage <= 0}
                    >
                      <ChevronLeft size={16} />
                    </button>
                    <span className="min-w-[80px] text-center font-bold text-slate-700 text-xs">
                      {Math.min(currentPage + 1, Math.max(1, pageCount || 1))} / {pageCount || 1}
                    </span>
                    <button 
                      className="hover:bg-slate-100 w-8 h-8 rounded-full flex items-center justify-center transition-colors disabled:opacity-30" 
                      onClick={() => setPage(currentPage + 1)}
                      disabled={pageCount === 0 || currentPage >= pageCount - 1}
                    >
                      <ChevronRight size={16} />
                    </button>
                 </div>
              </div>

           </div>

           {/* Right Floating Actions (More subtle) */}
           <div className="absolute right-4 top-4 flex flex-col gap-3 z-[80]">
              <button 
                onClick={() => setActivePanel(activePanel === 'edit' ? null : 'edit')}
                className={clsx(
                  "w-11 h-11 rounded-2xl flex items-center justify-center transition-all duration-200 shadow-md border",
                  activePanel === 'edit' 
                  ? 'bg-teal-600 border-teal-600 text-white ring-2 ring-teal-200' 
                  : 'bg-white/80 border-white/50 text-slate-500 hover:bg-white hover:text-teal-600'
                )}
                title="Editor"
              >
                <Edit3 size={20} />
              </button>
              <button 
                onClick={() => setActivePanel(activePanel === 'ai' ? null : 'ai')}
                className={clsx(
                  "w-11 h-11 rounded-2xl flex items-center justify-center transition-all duration-200 shadow-md border",
                  activePanel === 'ai' 
                  ? 'bg-teal-600 border-teal-600 text-white ring-2 ring-teal-200' 
                  : 'bg-white/80 border-white/50 text-slate-500 hover:bg-white hover:text-teal-600'
                )}
                title="AI Tools"
              >
                <Sparkles size={20} />
              </button>
           </div>

           {/* PANELS (Floating over the right side) */}
           {/* Basic Editor Panel */}
          <div className={clsx(
             "absolute right-[70px] top-4 bottom-24 w-[400px] bg-white/95 rounded-2xl shadow-2xl border border-white/50 overflow-hidden transition-all duration-300 origin-right flex flex-col z-[75]",
             activePanel === 'edit' ? 'translate-x-0 opacity-100' : 'translate-x-10 opacity-0 pointer-events-none hidden'
           )}>
              <div className="p-3 border-b border-slate-100 flex items-center justify-between bg-white/50">
                 <span className="font-bold text-slate-700 flex items-center gap-2 text-sm"><Edit3 size={14}/> Code Editor</span>
                 <button onClick={() => setActivePanel(null)} className="text-slate-400 hover:text-slate-600"><X size={14}/></button>
              </div>
              <div className="flex p-1.5 gap-1 bg-slate-50 border-b border-slate-100">
                {editorTabs.map((tab) => (
                  <button 
                    key={tab}
                    onClick={() => setEditTab(tab)}
                    className={clsx(
                      "flex-1 py-1.5 text-[10px] font-bold uppercase tracking-wider rounded-md transition-colors",
                      editTab === tab ? 'bg-white shadow-sm text-teal-600 border border-slate-200' : 'text-slate-400 hover:bg-white/50'
                    )}
                  >
                    {tab}
                  </button>
                ))}
              </div>
              <div className="flex-1 relative">
                <textarea 
                  className="absolute inset-0 w-full h-full bg-transparent p-4 text-xs font-mono text-slate-600 outline-none resize-none leading-relaxed"
                  value={editorFiles[editTab] || ''}
                  onChange={(e) => updateEditorFile(editTab, e.target.value)}
                  spellCheck={false}
                />
              </div>
              <div className="p-3 border-t border-slate-100 bg-white">
                <button 
                    onClick={handleUpdate}
                    className="w-full py-2 bg-teal-600 hover:bg-teal-700 text-white rounded-lg shadow-md transition-all flex items-center justify-center gap-2 text-xs font-bold group"
                >
                   <RefreshCw size={12} className={`group-hover:rotate-180 transition-transform duration-500 ${isCompiling ? 'animate-spin' : ''}`}/>
                   Compile & Update
                </button>
              </div>
           </div>

           {/* AI Tools Panel */}
          <div className={`absolute right-[70px] top-4 bottom-24 z-[70] w-[380px] bg-white/95 rounded-2xl shadow-2xl border border-white/50 overflow-hidden transition-all duration-300 origin-right flex flex-col ${
             activePanel === 'ai' ? 'translate-x-0 opacity-100' : 'translate-x-10 opacity-0 pointer-events-none hidden'
           }`}>
              <div className="p-3 border-b border-slate-100 flex items-center justify-between bg-white/50">
                 <span className="font-bold text-slate-700 flex items-center gap-2 text-sm"><Sparkles size={14} className="text-teal-600"/> AI Assistant</span>
                 <button onClick={() => setActivePanel(null)} className="text-slate-400 hover:text-slate-600"><X size={14}/></button>
              </div>
           <div className="flex-1 overflow-y-auto p-3">
             <div className="flex items-center gap-1 rounded-xl bg-slate-50 p-1 border border-slate-100">
               {([
                 { key: 'voice', label: 'Voice' },
                 { key: 'beautify', label: 'Beautify' },
                 { key: 'enrich', label: 'Web' },
               ] as const).map((t) => (
                 <button
                   key={t.key}
                   type="button"
                   onClick={() => setAiTab(t.key)}
                   className={`flex-1 h-8 rounded-lg text-[11px] font-bold transition-colors ${aiTab === t.key ? 'bg-white shadow-sm text-slate-900 border border-slate-200' : 'text-slate-500 hover:bg-white/50'}`}
                 >
                   {t.label}
                 </button>
               ))}
             </div>

             {aiTab === 'voice' && (
               <div className="mt-3 space-y-3">
                 <div className="text-xs font-bold text-slate-700">Voice Settings</div>
                <div className="rounded-xl border border-slate-200 bg-white p-3">
                  <div className="flex items-center justify-between gap-3">
                    <div className="min-w-0">
                      <div className="text-[11px] font-semibold text-slate-700">Auto TTS before Preview</div>
                      <div className="mt-0.5 text-[11px] text-slate-500">Generate audio before entering Preview.</div>
                    </div>
                    <button
                      type="button"
                      onClick={() => setAutoTtsBeforePreview(!autoTtsBeforePreview)}
                      className={clsx(
                        'relative inline-flex h-7 w-12 items-center rounded-full border transition-colors',
                        autoTtsBeforePreview ? 'bg-teal-600 border-teal-600' : 'bg-slate-200 border-slate-200'
                      )}
                      aria-pressed={autoTtsBeforePreview}
                      title={autoTtsBeforePreview ? 'Enabled' : 'Disabled'}
                    >
                      <span
                        className={clsx(
                          'inline-block h-5 w-5 transform rounded-full bg-white shadow-sm transition-transform',
                          autoTtsBeforePreview ? 'translate-x-6' : 'translate-x-1'
                        )}
                      />
                    </button>
                  </div>
                </div>
                 <div className="rounded-xl border border-slate-200 bg-white p-3">
                   <div className="flex items-center justify-between gap-2">
                     <div className="text-[11px] text-slate-500 font-medium">Record & clone voice</div>
                     <div className="text-[11px] text-slate-400 font-medium">{recorder.seconds ? `${recorder.seconds}s` : ''}</div>
                   </div>
                   <div className="mt-2 flex items-center gap-2">
                     <button
                       type="button"
                       onClick={() => (recorder.status === 'recording' ? recorder.stop() : recorder.start())}
                       className={`flex-1 h-9 rounded-xl text-xs font-semibold inline-flex items-center justify-center gap-2 transition-colors ${
                         recorder.status === 'recording'
                           ? 'bg-rose-600 text-white hover:bg-rose-700'
                           : 'bg-teal-600 text-white hover:bg-teal-700'
                       }`}
                     >
                       {recorder.status === 'recording' ? <StopCircle size={16} /> : <Mic size={16} />}
                       {recorder.status === 'recording' ? 'Stop' : 'Record'}
                     </button>
                     <button
                       type="button"
                       disabled={!voiceBlob || isCloningVoice}
                       onClick={cloneVoiceFromRecording}
                       className={`h-9 px-3 rounded-xl text-xs font-semibold border transition-colors ${
                         !voiceBlob || isCloningVoice
                           ? 'bg-white text-slate-300 border-slate-200 cursor-not-allowed'
                           : 'bg-white text-teal-700 border-teal-200 hover:bg-teal-50'
                       }`}
                     >
                       Use as Narrator
                     </button>
                   </div>
                   {recorder.error && <div className="mt-2 text-[11px] text-rose-600">{recorder.error}</div>}
                   <div className="mt-3 h-px bg-slate-100" />
                   <div className="text-[11px] text-slate-500 font-medium">Select narrator voice</div>
                   <div className="mt-2 space-y-2">
                     {voiceOptions.map((o) => (
                       <button
                         key={o.label}
                         type="button"
                         onClick={() => onSelectVoice(o.path)}
                         className={`w-full h-9 rounded-lg border text-xs font-semibold flex items-center justify-between px-3 transition-colors ${
                          selectedVoicePath === o.path ? 'border-teal-200 bg-teal-50 text-teal-700' : 'border-slate-200 bg-white text-slate-700 hover:bg-slate-50'
                         }`}
                       >
                         <span>{o.label}</span>
                         <span className="text-[10px] text-slate-400 truncate max-w-[160px]">{o.path}</span>
                       </button>
                     ))}
                   </div>
                   {!currentProject?.voice_prompt_path && (
                     <div className="mt-2 text-[11px] text-slate-500">
                       No cloned voice yet. Record in Requirements and click “Use as Narrator”.
                     </div>
                   )}
                 </div>
               </div>
             )}

             {aiTab === 'beautify' && (
              <div className="mt-3 space-y-3">
                <div className="text-xs font-bold text-slate-700">Beautify</div>
                <div className="rounded-xl border border-slate-200 bg-white p-3">
                  <div className="flex items-center justify-between">
                    <div className="text-[11px] text-slate-500 font-medium">Optimization Rounds</div>
                    <div className="flex items-center gap-3 rounded-lg border border-slate-200 bg-slate-50/50 px-2 py-1">
                      <button
                        type="button"
                        onClick={() => setBeautifyRounds(Math.max(1, beautifyRounds - 1))}
                        className="flex h-5 w-5 items-center justify-center rounded-md bg-white border border-slate-200 text-slate-600 hover:bg-slate-100 transition-colors"
                      >
                        <Minus size={12} />
                      </button>
                      <span className="text-xs font-bold text-slate-700 w-4 text-center">{beautifyRounds}</span>
                      <button
                        type="button"
                        onClick={() => setBeautifyRounds(Math.min(8, beautifyRounds + 1))}
                        className="flex h-5 w-5 items-center justify-center rounded-md bg-white border border-slate-200 text-slate-600 hover:bg-slate-100 transition-colors"
                      >
                        <Plus size={12} />
                      </button>
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={runBeautify}
                    className="mt-3 w-full h-9 rounded-xl bg-teal-600 text-white text-xs font-semibold hover:bg-teal-700 transition-all active:scale-[0.98]"
                  >
                    Run Optimization
                  </button>
                  <div className="mt-2 text-[11px] text-slate-500">
                   Use a vision model to batch-improve LaTeX layout based on the current PDF preview and recompile automatically.
                  </div>
                </div>
              </div>
            )}

             {aiTab === 'enrich' && (
               <div className="mt-3 space-y-3">
                 <div className="text-xs font-bold text-slate-700">Enrich</div>
                 <div className="rounded-xl border border-slate-200 bg-white p-3">
                  <div className="text-[11px] text-slate-500 font-medium">Collected slides: {collectedPages.size ? Array.from(collectedPages).sort((a, b) => a - b).map((x) => x + 1).join(', ') : 'None'}</div>
                  <div className="mt-1 text-[10px] text-slate-400 font-medium">These options only affect generated HTML (Web) and will not change the PDF.</div>

                  <div className="mt-3 rounded-2xl border border-slate-200 bg-gradient-to-br from-slate-50 to-teal-50/40 p-3">
                    <div className="flex items-center justify-between">
                      <div className="text-xs font-bold text-slate-800">HTML Web Enhance</div>
                      <div className="text-[10px] font-semibold text-slate-500">Enhancements</div>
                    </div>
                    <div className="mt-2 flex items-center justify-between rounded-xl border border-slate-200 bg-white px-3 py-2">
                      {/* <div className="text-[11px] font-semibold text-slate-600">Theme Preset</div> */}
                      <SlideThemeSelector value={htmlThemePreset} onChange={setHtmlThemePreset} />
                    </div>
                    <div className="mt-2 grid grid-cols-2 gap-2">
                      {(
                        [
                          { key: 'Image Focus', icon: ImageIcon },
                          { key: 'Auto Diagram', icon: Share2 },
                          { key: 'Table Viz', icon: Table2 },
                          { key: 'Text Keynote', icon: Type },
                          { key: 'Motion', icon: Zap },
                          { key: 'Auto Layout', icon: Sparkles },
                        ] as const
                      ).map(({ key, icon: Icon }) => {
                        const active = enrichEffects.includes(key);
                        return (
                          <button
                            key={key}
                            type="button"
                            onClick={() => setEnrichEffects((prev) => (prev.includes(key) ? prev.filter((x) => x !== key) : [...prev, key]))}
                            className={clsx(
                              'h-9 rounded-xl border text-[11px] font-semibold flex items-center justify-center gap-2 transition-all',
                              active
                                ? 'bg-teal-600 text-white border-teal-600 shadow-sm'
                                : 'bg-white text-slate-700 border-slate-200 hover:bg-slate-50'
                            )}
                          >
                            <Icon size={14} />
                            <span className="truncate">{key}</span>
                          </button>
                        );
                      })}
                    </div>

                    <div className="mt-3 rounded-2xl border border-slate-200 bg-white p-3">
                      <div className="flex items-center justify-between">
                        <div className="text-[11px] font-bold text-slate-800">Visual FX</div>
                        <button
                          type="button"
                          onClick={() => setVisualFx((v) => !v)}
                          className={clsx(
                            'h-7 px-3 rounded-full text-[11px] font-semibold border transition-colors',
                            visualFx ? 'bg-teal-600 text-white border-teal-600' : 'bg-slate-50 text-slate-600 border-slate-200 hover:bg-slate-100'
                          )}
                        >
                          {visualFx ? 'Enabled' : 'Disabled'}
                        </button>
                      </div>
                      <div className="mt-2 text-[11px] text-slate-500">
                        When enabled, the system generates content-driven poster/background visuals.
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={onGoClick}
                      disabled={!previewImages.length}
                      className={clsx(
                        'mt-3 w-full h-9 rounded-xl text-xs font-semibold transition-colors relative z-10 pointer-events-auto',
                        previewImages.length ? 'bg-teal-600 text-white hover:bg-teal-700' : 'bg-slate-100 text-slate-400 cursor-not-allowed'
                      )}
                    >
                      Go!
                    </button>
                    <div className="mt-2 text-[11px] text-slate-500">Star pages in PDF mode, then switch to Web mode to view results.</div>
                  </div>

                 </div>
               </div>
             )}
           </div>
           </div>

        </div>

      </div>

      {/* Bottom Dock - Input Bar */}
      <div className="relative z-50 px-4 pb-6 pt-3">
        <div className="max-w-2xl mx-auto">
          <div className="bg-white rounded-2xl shadow-[0_8px_30px_rgba(0,0,0,0.08)] border border-slate-100 p-2 pl-4 flex items-center gap-3 transition-all focus-within:ring-2 focus-within:ring-teal-100 focus-within:border-teal-200">
            
            <div className="flex items-center gap-1 pr-2 border-r border-slate-100">
               <button className="p-2.5 text-teal-700 bg-teal-50 hover:bg-teal-100 rounded-xl transition-colors" title="Voice Input">
                  <Mic size={20} />
               </button>
            </div>

            <input 
              type="text" 
              placeholder="Describe changes (e.g. 'Make the title larger', 'Add a chart')..."
              className="flex-1 bg-transparent border-none outline-none text-slate-700 text-sm placeholder:text-slate-400 h-11"
              value={inputText}
              onChange={(e) => setInputText(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleCommand()}
              disabled={isThinking}
            />

            <button 
                onClick={handleCommand}
                disabled={isThinking}
                className="bg-teal-600 hover:bg-teal-700 text-white rounded-xl px-5 h-11 font-semibold text-sm shadow-md shadow-teal-200 transition-transform active:scale-95 flex items-center gap-2"
            >
              {isThinking ? (
                <RefreshCw size={16} className="animate-spin" />
              ) : (
                <Sparkles size={16} />
              )}
              {isThinking ? 'Processing' : 'Generate'}
            </button>
          </div>
        </div>
      </div>

      {isExportOpen && (
        <div className="absolute inset-0 z-[80] flex items-center justify-center bg-slate-800/20 p-4">
          <div className="w-full max-w-md rounded-2xl bg-white shadow-2xl ring-1 ring-slate-200 overflow-hidden">
            <div className="flex items-center justify-between px-5 py-4 border-b border-slate-100">
              <div className="text-sm font-bold text-slate-900">Choose Preview & Export Version</div>
              <button type="button" onClick={() => setIsExportOpen(false)} className="p-2 text-slate-400 hover:text-slate-700">
                <X size={16} />
              </button>
            </div>

            <div className="p-5 space-y-3">
              {(
                [
                  { key: 'static', title: 'Static Version (PDF)', desc: 'Preview and export using the PDF generated from LaTeX/Beamer.' },
                  { key: 'dynamic_prepend', title: 'Dynamic v1 (HTML before PDF)', desc: 'Insert the HTML page before the corresponding PDF page.' },
                  { key: 'dynamic_append', title: 'Dynamic v2 (HTML after PDF)', desc: 'Insert the HTML page after the corresponding PDF page.' },
                  { key: 'dynamic_replace', title: 'Dynamic v3 (Replace PDF with HTML)', desc: 'Replace the corresponding PDF page with HTML when available.' },
                ] as const
              ).map((o) => (
                <button
                  key={o.key}
                  type="button"
                  onClick={() => setExportChoice(o.key)}
                  className={`w-full text-left rounded-xl border px-4 py-3 transition-colors ${exportChoice === o.key ? 'border-teal-200 bg-teal-50' : 'border-slate-200 hover:bg-slate-50'}`}
                >
                  <div className="text-sm font-semibold text-slate-900">{o.title}</div>
                  <div className="mt-1 text-xs text-slate-500 leading-relaxed">{o.desc}</div>
                </button>
              ))}
            </div>

            <div className="flex items-center justify-between gap-3 px-5 py-4 border-t border-slate-100 bg-slate-50">
              <div className="flex items-center gap-3 min-w-0">
                <div className="min-w-0">
                  <div className="text-[11px] font-semibold text-slate-700">预生成指标/建议/提问</div>
                  <div className="mt-0.5 text-[11px] text-slate-500">关闭可跳过计算，直接进入预览。</div>
                </div>
                <button
                  type="button"
                  onClick={() => setPrecomputeInsightsBeforePreview(!precomputeInsightsBeforePreview)}
                  className={clsx(
                    'relative inline-flex h-7 w-12 items-center rounded-full border transition-colors flex-none',
                    precomputeInsightsBeforePreview ? 'bg-teal-600 border-teal-600' : 'bg-slate-200 border-slate-200'
                  )}
                  aria-pressed={precomputeInsightsBeforePreview}
                  title={precomputeInsightsBeforePreview ? 'Enabled' : 'Disabled'}
                >
                  <span
                    className={clsx(
                      'inline-block h-5 w-5 transform rounded-full bg-white shadow-sm transition-transform',
                      precomputeInsightsBeforePreview ? 'translate-x-6' : 'translate-x-1'
                    )}
                  />
                </button>
              </div>
              <div className="flex items-center justify-end gap-2">
              <button
                type="button"
                onClick={() => setIsExportOpen(false)}
                className="h-10 px-4 rounded-xl text-xs font-semibold text-slate-700 border border-slate-200 bg-white hover:bg-slate-50"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={async () => {
                  if (!currentProject) return;
                  setExportMode(exportChoice);
                  if (autoTtsBeforePreview) {
                    const speechRaw = String(editorFiles?.speech || '').trim();
                    const speechSegments = speechRaw ? speechRaw.split('<next>').map((s) => s.trim()) : [];
                    const maxN = Math.min(previewImages.length, speechSegments.length);
                    const pageIndices: number[] = [];
                    for (let i = 0; i < maxN; i += 1) {
                      if (!speechSegments[i]) continue;
                      pageIndices.push(i);
                    }
                    if (pageIndices.length > 0) {
                      setBusyLabel(`TTS (0/${pageIndices.length})`);
                      setBusyProgress(0);
                      try {
                        await generateTtsForPages(currentProject.project_id, pageIndices, {
                          onProgress(done, total) {
                            setBusyLabel(`TTS (${done}/${total})`);
                            setBusyProgress(Math.round((done / total) * 100));
                          },
                        });
                      } catch (e) {
                        setBusyLabel(e instanceof Error ? e.message : 'TTS failed');
                        setBusyProgress(null);
                        return;
                      }
                      setBusyLabel(null);
                      setBusyProgress(null);
                    }
                  }
                  setIsExportOpen(false);
                  await navigateTo('PREVIEW');
                }}
                className="h-10 px-4 rounded-xl text-xs font-semibold text-white bg-teal-600 hover:bg-teal-700"
              >
                Go to Preview
              </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default SlideEditorView;
