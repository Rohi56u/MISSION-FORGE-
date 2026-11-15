import React, { useState, useEffect, lazy, Suspense } from 'react';
import { Shell } from './components/layout/Shell';
import { CommandBridge } from './views/CommandBridge';

const AstrodynamicsLab = lazy(() =>
  import('./views/AstrodynamicsLab').then((m) => ({ default: m.AstrodynamicsLab }))
);

const SpacecraftDesigner = lazy(() =>
  import('./views/SpacecraftDesigner').then((m) => ({ default: m.SpacecraftDesigner }))
);

const CdfCollaboration = lazy(() =>
  import('./views/CdfCollaboration').then((m) => ({ default: m.CdfCollaboration }))
);

const FdirCapcomOperations = lazy(() =>
  import('./views/FdirCapcomOperations').then((m) => ({ default: m.FdirCapcomOperations }))
);

const MissionDossierCenter = lazy(() =>
  import('./views/MissionDossierCenter').then((m) => ({ default: m.MissionDossierCenter }))
);

const VALID_PATHS = ['/', '/trajectory', '/spacecraft', '/cdf', '/fdir', '/dossier'];

export const App: React.FC = () => {
  const [currentPath, setCurrentPath] = useState<string>(() => {
    if (typeof window !== 'undefined') {
      const path = window.location.pathname;
      if (VALID_PATHS.includes(path)) return path;
    }
    return '/';
  });

  useEffect(() => {
    const handlePopState = () => {
      const path = window.location.pathname;
      setCurrentPath(VALID_PATHS.includes(path) ? path : '/');
    };

    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, []);

  const handleNavigate = (path: string) => {
    setCurrentPath(path);
    if (typeof window !== 'undefined' && window.location.pathname !== path) {
      window.history.pushState({}, '', path);
    }
  };

  const renderCurrentView = () => {
    switch (currentPath) {
      case '/trajectory':
        return (
          <Suspense
            fallback={
              <div className="py-24 text-center text-slate-400 font-mono text-xs flex items-center justify-center space-x-2">
                <span className="w-2.5 h-2.5 rounded-full bg-accent animate-ping inline-block" />
                <span>INITIALIZING ASTRODYNAMICS LAB SUITE...</span>
              </div>
            }
          >
            <AstrodynamicsLab />
          </Suspense>
        );

      case '/spacecraft':
        return (
          <Suspense
            fallback={
              <div className="py-24 text-center text-slate-400 font-mono text-xs flex items-center justify-center space-x-2">
                <span className="w-2.5 h-2.5 rounded-full bg-accent animate-ping inline-block" />
                <span>LOADING SPACECRAFT VISUALIZER & COMPONENT LEDGER...</span>
              </div>
            }
          >
            <SpacecraftDesigner />
          </Suspense>
        );

      case '/cdf':
        return (
          <Suspense
            fallback={
              <div className="py-24 text-center text-slate-400 font-mono text-xs flex items-center justify-center space-x-2">
                <span className="w-2.5 h-2.5 rounded-full bg-accent animate-ping inline-block" />
                <span>CONNECTING TO CONCURRENT DESIGN FACILITY...</span>
              </div>
            }
          >
            <CdfCollaboration />
          </Suspense>
        );

      case '/fdir':
        return (
          <Suspense
            fallback={
              <div className="py-24 text-center text-slate-400 font-mono text-xs flex items-center justify-center space-x-2">
                <span className="w-2.5 h-2.5 rounded-full bg-accent animate-ping inline-block" />
                <span>INITIALIZING DETERMINISTIC FDIR & CAPCOM ADVISORY SUITE...</span>
              </div>
            }
          >
            <FdirCapcomOperations />
          </Suspense>
        );

      case '/dossier':
        return (
          <Suspense
            fallback={
              <div className="py-24 text-center text-slate-400 font-mono text-xs flex items-center justify-center space-x-2">
                <span className="w-2.5 h-2.5 rounded-full bg-accent animate-ping inline-block" />
                <span>MOUNTING MISSION DOSSIER & ARTIFACT EXPORT CENTER...</span>
              </div>
            }
          >
            <MissionDossierCenter />
          </Suspense>
        );

      default:
        return <CommandBridge />;
    }
  };

  return (
    <Shell currentPath={currentPath} onNavigate={handleNavigate}>
      {renderCurrentView()}
    </Shell>
  );
};

export default App;
