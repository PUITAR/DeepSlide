import { create } from 'zustand';
import type { ChatMessage, LogicEdge, LogicNode, Project, FileNode } from '../types';
import { 
  getProjectFiles, getFileContent, saveFileContent, 
  sendChatMessage, getChatHistory, updateNodes,
  getEditorFiles, saveEditorFiles, compileProject, getPreviewPages, sendEditorCommand,
  startGenerateProjectSlides, getGenerateProjectSlidesStatus,
  selectLogicChainCandidate,
  preparePreviewInsights,
  getPreviewInsightsStatus
} from '../api/projects';

export type AppState = 'UPLOAD' | 'REQUIREMENTS' | 'LOGIC_CHAIN' | 'EDITING' | 'PREVIEW';

export type ExportMode = 'static' | 'dynamic_prepend' | 'dynamic_append' | 'dynamic_replace';

export type CompilerError = { message?: string; file?: string; line?: number | null };

interface ProjectState {
  appState: AppState;
  exportMode: ExportMode;
  autoTtsBeforePreview: boolean;
  precomputeInsightsBeforePreview: boolean;

  busyLabel: string | null;
  busyProgress: number | null; // 0-100
  
  projects: Project[];
  currentProject: Project | null;
  files: FileNode[];
  currentFile: string | null;
  fileContent: string;
  
  // Requirements State
  chatHistory: ChatMessage[];
  isChatting: boolean;
  logicChainCandidates: Array<{ candidate_id: string; title: string; reason?: string; nodes: LogicNode[]; edges: LogicEdge[] }>;
  
  // Logic Chain State
  nodes: LogicNode[];
  edges: LogicEdge[];
  processingNodeId: string | null;
  
  // Editor State
  editorFiles: {
    content: string;
    speech: string;
    title: string;
    base: string;
  };
  activePanel: 'edit' | 'ai' | null;
  previewMode: 'beamer' | 'html';
  previewImages: string[];
  currentPage: number;
  
  // Compiler State
  isCompiling: boolean;
  compilerErrors: CompilerError[];
  
  // AI State
  isThinking: boolean;
  
  isLoadingFiles: boolean;
  
  setAppState: (state: AppState) => void;
  navigateTo: (state: AppState) => Promise<void>;
  setExportMode: (mode: ExportMode) => void;
  setAutoTtsBeforePreview: (enabled: boolean) => void;
  setPrecomputeInsightsBeforePreview: (enabled: boolean) => void;
  setBusyLabel: (label: string | null) => void;
  setBusyProgress: (progress: number | null) => void;
  setProjects: (projects: Project[]) => void;
  setCurrentProject: (project: Project) => void;
  
  // Actions
  loadFiles: (projectId: string) => Promise<void>;
  selectFile: (projectId: string, filePath: string) => Promise<void>;
  updateFileContent: (content: string) => void;
  saveCurrentFile: () => Promise<void>;
  
  // Editor Actions
  loadEditorFiles: () => Promise<void>;
  updateEditorFile: (file: 'content' | 'speech' | 'title' | 'base', content: string) => void;
  saveEditorState: () => Promise<void>;
  compile: () => Promise<void>;
  executeCommand: (instruction: string) => Promise<void>;
  setActivePanel: (panel: 'edit' | 'ai' | null) => void;
  setPreviewMode: (mode: 'beamer' | 'html') => void;
  setPage: (page: number) => void;
  
  // Requirements Actions
  sendRequirementMessage: (message: string) => Promise<void>;
  loadChatHistory: () => Promise<void>;
  chooseLogicChainCandidate: (candidateId: string) => Promise<void>;
  
  // Logic Chain Actions
  updateProjectNodes: (nodes: LogicNode[], edges?: LogicEdge[]) => Promise<void>;
  setEdges: (edges: LogicEdge[]) => void;
}

export const useProjectStore = create<ProjectState>((set, get) => ({
  appState: 'UPLOAD',

  exportMode: 'static',
  autoTtsBeforePreview: (() => {
    try {
      const raw = localStorage.getItem('ds_auto_tts_before_preview');
      if (raw === '0') return false;
      if (raw === '1') return true;
      return true;
    } catch {
      return true;
    }
  })(),
  precomputeInsightsBeforePreview: (() => {
    try {
      const raw = localStorage.getItem('ds_precompute_preview_insights');
      if (raw === '0') return false;
      if (raw === '1') return true;
      return true;
    } catch {
      return true;
    }
  })(),

  busyLabel: null,
  busyProgress: null,
  
  projects: [],
  currentProject: null,
  files: [],
  currentFile: null,
  fileContent: '',
  
  chatHistory: [],
  isChatting: false,
  logicChainCandidates: [],
  
  nodes: [],
  edges: [],
  processingNodeId: null,
  
  editorFiles: { content: '', speech: '', title: '', base: '' },
  activePanel: null,
  previewMode: 'beamer',
  previewImages: [],
  currentPage: 0,
  
  isCompiling: false,
  compilerErrors: [],
  
  isThinking: false,
  
  isLoadingFiles: false,

  setAppState: (state) => set({ appState: state }),
  navigateTo: async (state) => {
    const { appState } = get();
    if (appState === state) return;
    if (appState === 'EDITING') {
      await get().saveEditorState();
    }
    if (state === 'PREVIEW') {
      const { currentProject } = get();
      if (currentProject?.project_id) {
        if (!get().precomputeInsightsBeforePreview) {
          set({ appState: state });
          return;
        }
        let prepared = false;
        try {
          set({ busyLabel: 'Preparing Preview…', busyProgress: 0 });
          await preparePreviewInsights(currentProject.project_id, { include_llm: true, force: false });
          const t0 = Date.now();
          while (true) {
            const s = await getPreviewInsightsStatus(currentProject.project_id);
            const status = String(s?.status || '');
            const prog = s?.progress;
            if (prog && typeof prog.current === 'number' && typeof prog.total === 'number' && prog.total > 0) {
              const pct = Math.max(0, Math.min(100, Math.round((prog.current / prog.total) * 100)));
              set({ busyProgress: pct });
            } else {
              set({ busyProgress: null });
            }
            if (status === 'done') break;
            if (status === 'error') throw new Error(String(s?.error || 'Preview preparation failed'));
            if (Date.now() - t0 > 120_000) throw new Error('Preview preparation timeout');
            await new Promise((r) => setTimeout(r, 800));
          }
          prepared = true;
        } catch (e: any) {
          const msg = String(e?.message || e || 'Preview preparation failed');
          set({ busyLabel: msg, busyProgress: null });
          setTimeout(() => set({ busyLabel: null, busyProgress: null }), 1500);
          return;
        } finally {
          if (prepared) set({ busyLabel: null, busyProgress: null });
        }
      }
    }
    set({ appState: state });
  },
  setExportMode: (mode) => set({ exportMode: mode }),
  setAutoTtsBeforePreview: (enabled) => {
    try {
      localStorage.setItem('ds_auto_tts_before_preview', enabled ? '1' : '0');
    } catch {}
    set({ autoTtsBeforePreview: enabled });
  },
  setPrecomputeInsightsBeforePreview: (enabled) => {
    try {
      localStorage.setItem('ds_precompute_preview_insights', enabled ? '1' : '0');
    } catch {}
    set({ precomputeInsightsBeforePreview: enabled });
  },
  setBusyLabel: (label) => set({ busyLabel: label, busyProgress: null }),
  setBusyProgress: (progress) => set({ busyProgress: progress }),
  setProjects: (projects) => set({ projects }),
  setCurrentProject: (project) => {
    set({ currentProject: project });
    if (project.nodes) set({ nodes: project.nodes });
    set({ edges: project.edges || [] }); 
  },
  
  loadFiles: async (projectId) => {
    set({ isLoadingFiles: true });
    try {
      const files = await getProjectFiles(projectId);
      set({ files });
    } finally {
      set({ isLoadingFiles: false });
    }
  },

  selectFile: async (projectId, filePath) => {
    const content = await getFileContent(projectId, filePath);
    set({ currentFile: filePath, fileContent: content });
  },

  updateFileContent: (content) => set({ fileContent: content }),

  saveCurrentFile: async () => {
    const { currentProject, currentFile, fileContent } = get();
    if (!currentProject || !currentFile) return;
    await saveFileContent(currentProject.project_id, currentFile, fileContent);
  },

  // Editor Actions
  loadEditorFiles: async () => {
    const { currentProject } = get();
    if (!currentProject) return;
    try {
      set({ busyLabel: 'Loading editor…' });
      const res = await getEditorFiles(currentProject.project_id);
      set({ editorFiles: { ...get().editorFiles, ...res.files } });
      
      // Load preview initially
      const prev = await getPreviewPages(currentProject.project_id);
      set({ previewImages: prev.pages });
      
    } catch (e) {
      console.error(e);
    } finally {
      set({ busyLabel: null });
    }
  },
  
  updateEditorFile: (file, content) => {
    set(state => ({ editorFiles: { ...state.editorFiles, [file]: content } }));
  },
  
  saveEditorState: async () => {
    const { currentProject, editorFiles } = get();
    if (!currentProject) return;
    await saveEditorFiles(currentProject.project_id, editorFiles);
  },
  
  compile: async () => {
    const { currentProject } = get();
    if (!currentProject) return;
    
    await get().saveEditorState();
    
    set({ isCompiling: true, compilerErrors: [] });
    try {
      set({ busyLabel: 'Compiling…' });
      const response = await compileProject(currentProject.project_id);
      if (response.success) {
         // Reload preview
         const prev = await getPreviewPages(currentProject.project_id);
         set({ previewImages: prev.pages });
      } else {
        set({ compilerErrors: response.errors });
      }
    } catch (e) {
      console.error(e);
      alert('Compilation error');
    } finally {
      set({ isCompiling: false });
      set({ busyLabel: null });
    }
  },
  
  setPage: (page) => set({ currentPage: page }),
  
  executeCommand: async (instruction) => {
    const { currentProject, currentPage } = get();
    if (!currentProject) return;
    
    set({ isThinking: true });
    try {
        set({ busyLabel: 'Processing…' });
        const res = await sendEditorCommand(currentProject.project_id, instruction, currentPage);
        if (res.success) {
            // Reload files and preview
            await get().loadEditorFiles();
            // Compile automatically
            await get().compile();
        }
    } catch (e) {
        console.error(e);
        alert("AI Command failed");
    } finally {
        set({ isThinking: false });
        set({ busyLabel: null });
    }
  },
  
  setActivePanel: (panel) => set({ activePanel: panel }),
  setPreviewMode: (mode) => set({ previewMode: mode }),
  
  // Requirements
  sendRequirementMessage: async (message) => {
      const { currentProject } = get();
      if (!currentProject) return;
      
      set({ isChatting: true });
      set({ logicChainCandidates: [] });
      set(state => ({ chatHistory: [...state.chatHistory, {role: 'user', content: message}] }));
      
      try {
          set({ busyLabel: 'Thinking…' });
          const res = await sendChatMessage(currentProject.project_id, message);
          set(state => ({ chatHistory: [...state.chatHistory, {role: 'assistant', content: res.response}] }));

          if (res.logic_chain_candidates && res.logic_chain_candidates.length) {
              set({ logicChainCandidates: res.logic_chain_candidates });
          }
      } catch (e) {
          const msg = String((e as any)?.response?.data?.detail || (e as any)?.message || e || 'Request failed');
          console.error(e);
          set(state => ({ chatHistory: [...state.chatHistory, { role: 'assistant', content: `Request failed: ${msg}` }] }));
      } finally {
          set({ isChatting: false });
          set({ busyLabel: null });
      }
  },

  chooseLogicChainCandidate: async (candidateId) => {
      const { currentProject } = get();
      if (!currentProject) return;
      set({ busyLabel: 'Selecting…' });
      try {
          const updated = await selectLogicChainCandidate(currentProject.project_id, candidateId);
          set({ currentProject: updated });
          set({ logicChainCandidates: [] });
          if (updated.nodes) set({ nodes: updated.nodes });
          if (updated.edges) set({ edges: updated.edges });
          set({ appState: 'LOGIC_CHAIN' });
      } finally {
          set({ busyLabel: null });
      }
  },
  
  loadChatHistory: async () => {
      const { currentProject } = get();
      if (!currentProject) return;
      const res = await getChatHistory(currentProject.project_id);
      set({ chatHistory: res.history });
  },
  
  updateProjectNodes: async (nodes, edges = []) => {
      const { currentProject } = get();
      if (!currentProject) return;
      
      set({ nodes, edges });
      set({ busyLabel: 'Saving logic chain…' });
      await updateNodes(currentProject.project_id, nodes, edges);
      
      // Trigger generation
      set({ isThinking: true, processingNodeId: nodes[0]?.node_id || null });
      try {
        set({ busyLabel: 'Starting generation…' });
        await startGenerateProjectSlides(currentProject.project_id);

        const sleep = (ms: number) => new Promise((r) => window.setTimeout(r, ms));
        let compileRes: any = null;
        for (let t = 0; t < 1200; t++) {
          const st = await getGenerateProjectSlidesStatus(currentProject.project_id);
          const status = String(st.status || 'idle');
          if (status === 'generating') {
            const idx = Number(st.current_index ?? 0);
            const safeIdx = Number.isFinite(idx) ? Math.max(0, Math.min(nodes.length - 1, idx)) : 0;
            set({ processingNodeId: nodes[safeIdx]?.node_id || null, busyLabel: `Generating: ${nodes[safeIdx]?.title || st.current_title || ''}` });
          } else if (status === 'compiling') {
            set({ processingNodeId: null, busyLabel: 'Compiling…' });
          } else if (status === 'done') {
            compileRes = st.compile || null;
            break;
          } else if (status === 'error') {
            set({ compilerErrors: [{ message: st.error || 'Generation failed' }], processingNodeId: null });
            compileRes = null;
            break;
          }
          await sleep(700);
        }

        if (!compileRes) {
          compileRes = await compileProject(currentProject.project_id);
        }

        if (compileRes?.success) {
          const prev = await getPreviewPages(currentProject.project_id);
          set({ previewImages: prev.pages, compilerErrors: [] });
        } else {
          set({ compilerErrors: compileRes?.errors || [{ message: 'Compilation failed' }] });
        }
      } catch (e) {
        console.error("Failed to generate slides:", e);
        // Fallthrough to allow editing empty slides
      } finally {
        set({ isThinking: false, processingNodeId: null });
        set({ busyLabel: null });
      }
      
      set({ appState: 'EDITING' });
      await get().loadEditorFiles();
  },
  
  setEdges: (edges) => set({ edges })
}));
