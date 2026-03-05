import React from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import { useProjectStore } from './store/useProjectStore';
import UploadView from './components/phases/UploadView';
import RequirementsView from './components/phases/RequirementsView';
import LogicChainView from './components/phases/LogicChainView';
import SlideEditorView from './components/phases/SlideEditorView';
import PreviewView from './components/phases/PreviewView';
import { GlobalBusyOverlay } from './components/GlobalBusyOverlay';
import Workspace from './pages/Workspace';
import { GlobalMistCanvas } from './components/GlobalMistCanvas';

const MainFlow: React.FC = () => {
  const { appState, currentProject } = useProjectStore();

  // If no project, force upload
  if (!currentProject) {
      return <UploadView />;
  }

  switch (appState) {
    case 'UPLOAD':
      return <UploadView />;
    case 'REQUIREMENTS':
      return <RequirementsView />;
    case 'LOGIC_CHAIN':
      return <LogicChainView />;
    case 'EDITING':
      return <SlideEditorView />;
    case 'PREVIEW':
      return <PreviewView />;
    default:
      return <UploadView />;
  }
};

const App: React.FC = () => {
  return (
    <Router>
      <GlobalMistCanvas />
      <GlobalBusyOverlay />
      <Routes>
        <Route path="/" element={<MainFlow />} />
        {/* Workspace route for direct file access if needed */}
        <Route path="/project/:projectId" element={<Workspace />} />
      </Routes>
    </Router>
  );
};

export default App;
