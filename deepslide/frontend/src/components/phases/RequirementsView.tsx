import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useProjectStore } from '../../store/useProjectStore';
import { Loader2, Mic, Send, StopCircle, User, FileText, ChevronRight, CornerDownLeft } from 'lucide-react';
import MarkdownRenderer from '../MarkdownRenderer';
import { useAudioRecorder } from '../../hooks/useAudioRecorder';
import { transcribeAudio } from '../../api/audio';
import { motion, AnimatePresence } from 'framer-motion';
import clsx from 'clsx';
import { StageNav } from '../StageNav';

const RequirementsView: React.FC = () => {
  const { chatHistory, sendRequirementMessage, isChatting, currentProject, logicChainCandidates, chooseLogicChainCandidate } = useProjectStore();
  const [input, setInput] = useState('');
  const [isTranscribing, setIsTranscribing] = useState(false);
  const [isCloning, setIsCloning] = useState(false);
  const [transcribeError, setTranscribeError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const recorder = useAudioRecorder();

  // New state for handling recorded audio actions
  const [pendingAudio, setPendingAudio] = useState<Blob | null>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [chatHistory, isChatting, isTranscribing, pendingAudio]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isChatting) return;
    
    const msg = input;
    setInput('');
    setPendingAudio(null); // Clear pending audio on send
    await sendRequirementMessage(msg);
  };

  // Watch recorder blob
  useEffect(() => {
    if (recorder.lastBlob) {
      setPendingAudio(recorder.lastBlob);
    }
  }, [recorder.lastBlob]);

  const handleTranscribe = async () => {
    if (!pendingAudio || !currentProject) return;
    setIsTranscribing(true);
    setTranscribeError(null);
    try {
      const res = await transcribeAudio(currentProject.project_id, pendingAudio, 'zh');
      const text = (res?.text || '').trim();
      if (!text) {
        setTranscribeError('No text recognized');
        return;
      }
      setInput((prev) => {
        const p = (prev || '').trim();
        return p ? `${p} ${text}` : text;
      });
      // We keep pendingAudio in case they want to clone it too, 
      // or we can clear it if we assume transcribe consumes it.
      // Let's keep it for now.
    } catch {
      setTranscribeError('Transcription failed');
    } finally {
      setIsTranscribing(false);
    }
  };

  const handleCloneVoice = async () => {
    if (!pendingAudio || !currentProject) return;
    setIsCloning(true);
    try {
      // Pass saveVoice=true
      await transcribeAudio(currentProject.project_id, pendingAudio, 'zh', true);
      alert('Voice cloned successfully! This voice will be used for narration.');
    } catch (e) {
      console.error(e);
      alert('Failed to clone voice.');
    } finally {
      setIsCloning(false);
    }
  };

  const splitTwoLines = (text: string, maxTokens = 10) => {
    const tokens = String(text || '').match(/[A-Za-z0-9]+|[\u4e00-\u9fff]+/g) || [];
    const top = tokens.slice(0, maxTokens);
    const split = Math.ceil(top.length / 2) || 1;
    return { a: top.slice(0, split).join(' '), b: top.slice(split).join(' ') };
  };

  const chunk = (arr: any[], size: number) => {
    const out: any[][] = [];
    for (let i = 0; i < arr.length; i += size) out.push(arr.slice(i, i + size));
    return out;
  };

  const LogicChainCard = ({ c }: { c: any }) => {
    const nodes = Array.isArray(c?.nodes) ? c.nodes : [];
    const mini = useMemo(() => {
      const take = nodes.slice(0, 10);
      const rows = chunk(take, 4);
      return { rows, total: nodes.length };
    }, [nodes]);
    return (
      <button
        type="button"
        onClick={() => chooseLogicChainCandidate(String(c.candidate_id))}
        className="w-full text-left rounded-3xl bg-white hover:shadow-md transition-all px-5 py-4"
      >
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="text-sm font-extrabold text-slate-900">{String(c.title || 'Logic Chain')}</div>
            <div className="mt-0.5 text-[11px] font-semibold text-slate-500">{String(c.reason || '')}</div>
          </div>
          <div className="text-[10px] font-bold text-teal-700">Select</div>
        </div>

        <div className="mt-3 rounded-2xl border border-slate-200 bg-slate-50 p-3 overflow-x-auto">
          <div className="min-w-[620px] space-y-2">
            {mini.rows.map((row: any[], r: number) => {
              const rev = r % 2 === 1;
              const cells = rev ? [...row].reverse() : row;
              return (
                <div key={r} className="flex items-start">
                  <div className="flex items-center gap-2">
                    {cells.map((n: any, i: number) => {
                      const t = splitTwoLines(String(n?.title || ''), 10);
                      return (
                        <div key={String(n?.node_id || i)} className="flex items-center gap-2">
                          <div className="min-h-10 px-3 py-1.5 rounded-2xl bg-white border border-slate-200 text-[10px] font-semibold text-slate-700 flex flex-col justify-center max-w-[190px]">
                            <div className="truncate leading-[1.25]">{t.a || '—'}</div>
                            <div className="truncate leading-[1.25] mt-1">{t.b || ''}</div>
                          </div>
                          {i < cells.length - 1 && <ChevronRight className="h-4 w-4 text-slate-300" />}
                        </div>
                      );
                    })}
                  </div>
                  {r === 0 && mini.rows.length > 1 && (
                    <div className="flex-1 flex justify-end pr-2">
                      <CornerDownLeft className="h-4 w-4 text-slate-300" />
                    </div>
                  )}
                </div>
              );
            })}
            {mini.total > 10 && <div className="mt-2 text-[10px] font-semibold text-slate-400">…</div>}
          </div>
        </div>
      </button>
    );
  };

  return (
    <div className="h-screen bg-transparent flex flex-col">
      <StageNav />

      {/* Chat Area */}
      <div className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-6 bg-transparent scroll-smooth">
        {chatHistory.map((msg, idx) => (
          <motion.div 
            key={idx} 
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            className={`flex items-start gap-4 ${msg.role === 'user' ? 'flex-row-reverse' : ''}`}
          >
            <div
              className={clsx(
                "h-9 w-9 shrink-0 rounded-full flex items-center justify-center shadow-sm overflow-hidden",
                msg.role === 'user' ? 'bg-teal-600 text-white' : 'bg-white border border-slate-200'
              )}
            >
              {msg.role === 'user' ? <User className="h-5 w-5" /> : <img src="/api/v1/assets/logo.jpg" alt="DeepSlide" className="h-full w-full object-cover" />}
            </div>
            <div
              className={clsx(
                "max-w-[85%] sm:max-w-[75%] rounded-2xl px-5 py-3.5 text-sm leading-relaxed shadow-sm",
                msg.role === 'user'
                  ? 'bg-teal-600 text-white rounded-tr-sm'
                  : 'bg-white border border-slate-200 text-slate-800 rounded-tl-sm'
              )}
            >
              {msg.role === 'user' ? (
                <div className="whitespace-pre-wrap">{msg.content}</div>
              ) : (
                <div className="markdown-content prose prose-sm max-w-none prose-slate">
                  <MarkdownRenderer content={msg.content} />
                </div>
              )}
            </div>
          </motion.div>
        ))}

        {(isChatting || isTranscribing) && (
          <motion.div 
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="flex items-start gap-4"
          >
            <div className="h-9 w-9 shrink-0 rounded-full bg-white border border-slate-200 flex items-center justify-center shadow-sm overflow-hidden">
              <img src="/api/v1/assets/logo.jpg" alt="DeepSlide" className="h-full w-full object-cover" />
            </div>
            <div className="bg-white border border-slate-200 px-4 py-3 rounded-2xl rounded-tl-sm flex items-center gap-3 shadow-sm">
              <Loader2 className="h-4 w-4 animate-spin text-teal-600" />
              <div className="text-sm font-medium text-slate-600">
                {isTranscribing ? 'Transcribing audio...' : 'Thinking...'}
              </div>
            </div>
          </motion.div>
        )}

        {!!logicChainCandidates.length && (
          <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="w-full max-w-[1950px] mx-auto">
            <div className="rounded-3xl bg-white/0 p-0 shadow-none">
              <div className="flex items-center justify-between">
                <div>
                  <div className="text-xs font-extrabold text-slate-900">Logic Chain Suggestions</div>
                  <div className="mt-0.5 text-[11px] font-semibold text-slate-500">Pick one to enter Stage 2. Ask for changes in chat to regenerate.</div>
                </div>
              </div>
              <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-4">
                {logicChainCandidates.slice(0, 4).map((c: any) => (
                  <LogicChainCard key={String(c.candidate_id)} c={c} />
                ))}
              </div>
            </div>
          </motion.div>
        )}
        
        <div ref={bottomRef} />
      </div>

      {/* Input Area */}
      <div className="flex-none bg-transparent p-4 sm:p-6">
        <div className="max-w-4xl mx-auto space-y-4">
          
          {/* Audio Controls (If recorded) */}
          <AnimatePresence>
            {pendingAudio && !isChatting && (
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: 'auto', opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                className="overflow-hidden"
              >
                <div className="flex items-center gap-3 p-3 bg-slate-50 rounded-xl border border-slate-200 mb-2">
                   <div className="h-8 w-8 rounded-full bg-teal-100 flex items-center justify-center">
                     <Mic className="h-4 w-4 text-teal-700" />
                   </div>
                   <div className="flex-1 min-w-0">
                      <div className="text-xs font-semibold text-slate-700">Audio Recorded</div>
                      <div className="text-xs text-slate-400">Ready to transcribe or clone</div>
                   </div>
                   <div className="flex items-center gap-2">
                      <button 
                        type="button"
                        onClick={handleTranscribe}
                        disabled={isTranscribing}
                        className="px-3 py-1.5 rounded-lg bg-white border border-slate-200 text-xs font-semibold text-slate-700 hover:bg-slate-50 hover:border-slate-300 transition-colors flex items-center gap-1.5"
                      >
                        <FileText className="h-3.5 w-3.5" />
                        Transcribe
                      </button>
                      <button 
                        type="button"
                        onClick={handleCloneVoice}
                        disabled={isCloning}
                        className="px-3 py-1.5 rounded-lg bg-teal-50 border border-teal-100 text-xs font-semibold text-teal-700 hover:bg-teal-100 transition-colors flex items-center gap-1.5"
                      >
                        {isCloning ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <User className="h-3.5 w-3.5" />}
                        Use as Narrator
                      </button>
                   </div>
                </div>
                {transcribeError && (
                  <div className="px-3 pb-2">
                    <div className="text-[11px] font-semibold text-rose-600">{transcribeError}</div>
                  </div>
                )}
              </motion.div>
            )}
          </AnimatePresence>

          {/* Main Input Form */}
          <form onSubmit={handleSubmit} className="relative flex items-end gap-2 bg-white p-2 rounded-2xl shadow-[0_8px_30px_rgba(0,0,0,0.08)] border border-slate-100 focus-within:ring-2 focus-within:ring-teal-100 focus-within:border-teal-200 transition-all">
             {/* Record Button */}
             <button
               type="button"
               onClick={recorder.status === 'recording' ? recorder.stop : () => { setPendingAudio(null); recorder.start(); }}
               disabled={isChatting || isTranscribing}
               className={clsx(
                 "flex-none h-10 w-10 rounded-xl flex items-center justify-center transition-all duration-200",
                 recorder.status === 'recording'
                   ? "bg-rose-500 text-white animate-pulse shadow-lg shadow-rose-200"
                   : "text-slate-400 hover:text-teal-600 hover:bg-teal-50"
               )}
             >
               {recorder.status === 'recording' ? <StopCircle className="h-5 w-5" /> : <Mic className="h-5 w-5" />}
             </button>

             {/* Text Input */}
             <input
               type="text"
               value={input}
               onChange={(e) => setInput(e.target.value)}
               placeholder={recorder.status === 'recording' ? `Recording... ${recorder.seconds}s` : "Type your requirements (audience, duration, style)..."}
               className="flex-1 bg-transparent border-none h-10 px-2 text-sm text-slate-800 placeholder:text-slate-400 focus:ring-0"
               disabled={isChatting || isTranscribing}
             />

             {/* Send Button */}
             <button
               type="submit"
               disabled={!input.trim() || isChatting || isTranscribing}
               className={clsx(
                 "flex-none h-10 w-10 rounded-xl flex items-center justify-center transition-all duration-200 shadow-sm",
                 !input.trim() || isChatting
                   ? "bg-slate-100 text-slate-300 cursor-not-allowed"
                  : "bg-teal-600 text-white hover:bg-teal-700 shadow-lg active:scale-95"
               )}
             >
               {isChatting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4 ml-0.5 opacity-90" />}
             </button>
          </form>
          
          <div className="text-center">
            <p className="text-[10px] font-medium text-slate-400">
               {recorder.status === 'recording' ? 'Recording in progress...' : 'AI can help refine your presentation structure based on the paper.'}
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};

export default RequirementsView;
