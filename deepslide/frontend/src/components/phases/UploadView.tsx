import React, { useMemo, useState } from 'react';
import { useProjectStore } from '../../store/useProjectStore';
import { createProjectWithPackageUpload, createProjectWithUpload } from '../../api/projects';
import { ArrowRight, CheckCircle2, FileArchive, FileCode, FileText, Loader2, Presentation, ChevronDown, ChevronUp } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import clsx from 'clsx';

const UploadView: React.FC = () => {
  const { setCurrentProject, setAppState, loadChatHistory, currentProject, loadEditorFiles } = useProjectStore();
  const [isUploading, setIsUploading] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [isDragOver, setIsDragOver] = useState(false);
  const [isAbstractExpanded, setIsAbstractExpanded] = useState(false);
  const [uploadKind, setUploadKind] = useState<'paper' | 'package'>('paper');

  const accept = uploadKind === 'package'
    ? '.zip,.tar,.gz,.rar,.7z,.iso'
    : '.zip,.tar,.gz,.rar,.7z,.iso,.tex,.md,.docx,.pptx';

  const supportHint = uploadKind === 'package'
    ? 'Supports .zip / .tar / .gz / .rar / .7z'
    : 'Supports .zip / .tar / .gz / .rar / .7z / .tex / .docx / .pptx / .md';

  const analysis = useMemo(() => {
    const a = currentProject?.analysis;
    if (!a) return null;
    const main = a.main_file ? String(a.main_file) : '';
    const abstract = a.abstract ? String(a.abstract) : '';
    const nodes = Array.isArray(currentProject?.nodes) ? currentProject?.nodes : [];
    return { main, abstract, nodeCount: nodes?.length || 0 };
  }, [currentProject]);

  const handleUpload = async (e?: React.FormEvent) => {
    e?.preventDefault();
    if (!file) return;

    // Auto-generate name from filename (remove extension)
    const name = file.name.replace(/\.[^/.]+$/, "");

    setIsUploading(true);
    try {
      const project = uploadKind === 'package'
        ? await createProjectWithPackageUpload(name, file)
        : await createProjectWithUpload(name, file);
      setCurrentProject(project);

      if (uploadKind === 'package') {
        setAppState('PREVIEW');
        await loadEditorFiles();
      }

      // We stay on this view but show success state
    } catch (error) {
      console.error(error);
      alert('Upload failed');
    } finally {
      setIsUploading(false);
    }
  };

  const goNext = async () => {
    if (!currentProject) return;
    setAppState('REQUIREMENTS');
    await loadChatHistory();
  };

  const onDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(true);
  };

  const onDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
  };

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      setFile(e.dataTransfer.files[0]);
    }
  };

  const handleDivClick = () => {
    document.getElementById('file-upload-input')?.click();
  };

  return (
    <div className="min-h-screen bg-transparent flex flex-col items-center justify-center p-6 font-sans text-slate-900 selection:bg-teal-100 selection:text-teal-900">
      <div className="w-full max-w-[480px]">
        {/* Header */}
        <motion.div 
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, ease: "easeOut" }}
          className="mb-12 text-center"
        >
          <div className="mx-auto mb-4 h-14 w-14 rounded-2xl bg-white/80 border border-white/60 flex items-center justify-center shadow-xl shadow-teal-200 overflow-hidden">
            <img src="/assets/cover_icon.gif" alt="DeepSlide" className="h-full w-full object-cover" />
          </div>
          <h1 className="text-3xl font-bold tracking-tight text-slate-900">DeepSlide</h1>
          <p className="mt-2 text-slate-500 font-medium">Turn your materials into a presentation</p>
        </motion.div>

        {/* Main Card */}
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.5, delay: 0.1 }}
          className="relative group"
        >
           {/* Upload Area */}
           {!currentProject && (
            <form onSubmit={handleUpload} className="relative z-10">
              <div className="mb-4 flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => { setUploadKind('paper'); setFile(null); }}
                  className={clsx(
                    'flex-1 h-9 rounded-xl text-xs font-semibold border transition-colors',
                    uploadKind === 'paper'
                      ? 'bg-teal-600 text-white border-teal-600'
                      : 'bg-white text-slate-700 border-slate-200 hover:bg-slate-50'
                  )}
                >
                  Upload Paper Package
                </button>
                <button
                  type="button"
                  onClick={() => { setUploadKind('package'); setFile(null); }}
                  className={clsx(
                    'flex-1 h-9 rounded-xl text-xs font-semibold border transition-colors',
                    uploadKind === 'package'
                      ? 'bg-teal-600 text-white border-teal-600'
                      : 'bg-white text-slate-700 border-slate-200 hover:bg-slate-50'
                  )}
                >
                  Upload Project Package
                </button>
              </div>
              <div
                onClick={handleDivClick}
                onDragOver={onDragOver}
                onDragLeave={onDragLeave}
                onDrop={onDrop}
                className={clsx(
                  "relative rounded-3xl border-2 border-dashed transition-all duration-300 ease-out p-10 flex flex-col items-center justify-center text-center cursor-pointer bg-slate-50/50",
                  isDragOver ? "border-teal-500 bg-teal-50/50 scale-[1.02]" : "border-slate-200 hover:border-slate-300 hover:bg-slate-50",
                  file ? "border-slate-300 bg-white" : ""
                )}
              >
                <input
                  id="file-upload-input"
                  type="file"
                  onChange={(e) => setFile(e.target.files?.[0] || null)}
                  accept={accept}
                  className="hidden"
                  disabled={isUploading}
                />
                 
                 <div className={clsx("transition-all duration-300", file ? "scale-90 opacity-0 absolute" : "scale-100 opacity-100")}>
                    <div className="flex justify-center gap-6 mb-6">
                     <div className="flex flex-col items-center gap-2 group/icon">
                       <div className="h-12 w-12 rounded-2xl bg-slate-50 border border-slate-200 group-hover/icon:border-teal-200 group-hover/icon:bg-teal-50 flex items-center justify-center transition-colors">
                         <FileArchive className="h-6 w-6 text-slate-400 group-hover/icon:text-teal-600" />
                       </div>
                       <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider group-hover/icon:text-teal-600">Archive</span>
                     </div>
                      {uploadKind === 'paper' && (
                        <>
                          <div className="flex flex-col items-center gap-2 group/icon">
                            <div className="h-12 w-12 rounded-2xl bg-slate-50 border border-slate-200 group-hover/icon:border-blue-200 group-hover/icon:bg-blue-50 flex items-center justify-center transition-colors">
                              <FileText className="h-6 w-6 text-slate-400 group-hover/icon:text-blue-600" />
                            </div>
                            <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider group-hover/icon:text-blue-600">Word</span>
                          </div>
                          <div className="flex flex-col items-center gap-2 group/icon">
                            <div className="h-12 w-12 rounded-2xl bg-slate-50 border border-slate-200 group-hover/icon:border-orange-200 group-hover/icon:bg-orange-50 flex items-center justify-center transition-colors">
                              <Presentation className="h-6 w-6 text-slate-400 group-hover/icon:text-orange-600" />
                            </div>
                            <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider group-hover/icon:text-orange-600">PPT</span>
                          </div>
                          <div className="flex flex-col items-center gap-2 group/icon">
                            <div className="h-12 w-12 rounded-2xl bg-slate-50 border border-slate-200 group-hover/icon:border-purple-200 group-hover/icon:bg-purple-50 flex items-center justify-center transition-colors">
                              <FileCode className="h-6 w-6 text-slate-400 group-hover/icon:text-purple-600" />
                            </div>
                            <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider group-hover/icon:text-purple-600">MD</span>
                          </div>
                        </>
                      )}
                   </div>
                  <p className="text-base font-semibold text-slate-900">Click or Drag to Upload</p>
                   <p className="mt-1 text-sm text-slate-400">{supportHint}</p>
                 </div>

                 {file && (
                   <motion.div 
                     initial={{ opacity: 0, scale: 0.8 }}
                     animate={{ opacity: 1, scale: 1 }}
                     className="flex flex-col items-center"
                   >
                    <div className="h-16 w-16 mb-4 rounded-2xl bg-teal-50 border border-teal-100 flex items-center justify-center">
                      <FileArchive className="h-8 w-8 text-teal-700" />
                     </div>
                     <p className="text-base font-semibold text-slate-900 max-w-[200px] truncate">{file.name}</p>
                     <p className="mt-1 text-xs font-medium text-slate-400 uppercase tracking-wider">{Math.round(file.size / 1024)} KB</p>
                   </motion.div>
                 )}
               </div>

               <div className="mt-6">
                 <button
                   type="submit"
                   disabled={isUploading || !file}
                   className={clsx(
                    "w-full h-12 rounded-xl font-semibold text-sm transition-all duration-300 flex items-center justify-center gap-2 shadow-lg shadow-teal-200/50",
                     isUploading || !file
                       ? "bg-slate-100 text-slate-400 cursor-not-allowed shadow-none"
                      : "bg-teal-600 text-white hover:bg-teal-700 hover:-translate-y-0.5"
                   )}
                 >
                   {isUploading ? (
                     <>
                       <Loader2 className="h-4 w-4 animate-spin" />
                      <span>{uploadKind === 'package' ? 'Loading package...' : 'Analyzing Project...'}</span>
                     </>
                   ) : (
                     <>
                      <span>{uploadKind === 'package' ? 'Go to Preview' : 'Start Analysis'}</span>
                       <ArrowRight className="h-4 w-4" />
                     </>
                   )}
                 </button>
               </div>
             </form>
           )}

           {/* Analysis Result (Success State) */}
           {currentProject && analysis && (
             <motion.div
               initial={{ opacity: 0, y: 20 }}
               animate={{ opacity: 1, y: 0 }}
               className="bg-white rounded-3xl border border-slate-200 shadow-xl shadow-slate-200/40 overflow-hidden"
             >
               <div className="p-1 bg-gradient-to-r from-emerald-400 to-cyan-400" />
               <div className="p-8">
                 <div className="flex items-center gap-3 mb-6">
                   <div className="h-8 w-8 rounded-full bg-emerald-100 text-emerald-600 flex items-center justify-center">
                     <CheckCircle2 className="h-5 w-5" />
                   </div>
                   <span className="font-semibold text-slate-900">Analysis Complete</span>
                 </div>

                 <div className="space-y-4">
                   <div className="flex items-center justify-between p-4 rounded-2xl bg-slate-50 border border-slate-100">
                     <span className="text-sm font-medium text-slate-500">Main File</span>
                     <span className="text-sm font-semibold text-slate-900 font-mono">{analysis.main || 'N/A'}</span>
                   </div>

                   <div className="flex items-center justify-between p-4 rounded-2xl bg-slate-50 border border-slate-100">
                     <span className="text-sm font-medium text-slate-500">Structure</span>
                     <span className="text-sm font-semibold text-slate-900">{analysis.nodeCount} Chapters detected</span>
                   </div>

                   {analysis.abstract && (
                     <div className="p-4 rounded-2xl bg-slate-50 border border-slate-100 transition-all">
                       <div 
                         className="flex items-center justify-between cursor-pointer"
                         onClick={() => setIsAbstractExpanded(!isAbstractExpanded)}
                       >
                         <span className="text-sm font-medium text-slate-500">Abstract</span>
                         {isAbstractExpanded ? <ChevronUp className="h-4 w-4 text-slate-400" /> : <ChevronDown className="h-4 w-4 text-slate-400" />}
                       </div>
                       <AnimatePresence>
                         {isAbstractExpanded && (
                           <motion.div
                             initial={{ height: 0, opacity: 0, marginTop: 0 }}
                             animate={{ height: 'auto', opacity: 1, marginTop: 8 }}
                             exit={{ height: 0, opacity: 0, marginTop: 0 }}
                             className="overflow-hidden"
                           >
                             <p className="text-sm text-slate-600 leading-relaxed text-justify">{analysis.abstract}</p>
                           </motion.div>
                         )}
                       </AnimatePresence>
                       {!isAbstractExpanded && (
                          <p className="mt-2 text-sm text-slate-600 line-clamp-2">{analysis.abstract}</p>
                       )}
                     </div>
                   )}
                 </div>

                 <button
                   onClick={goNext}
                  className="mt-8 w-full h-12 rounded-xl bg-teal-600 text-white font-semibold text-sm flex items-center justify-center gap-2 hover:bg-teal-700 transition-all shadow-lg hover:shadow-xl hover:-translate-y-0.5"
                 >
                   <span>Start Requirements Chat</span>
                   <ArrowRight className="h-4 w-4" />
                 </button>
               </div>
             </motion.div>
           )}
        </motion.div>

      </div>
    </div>
  );
};

export default UploadView;
