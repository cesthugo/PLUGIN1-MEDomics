import React from 'react'
import ReactDOM from 'react-dom/client'
import { StarhePlugin } from './pages/StarhePlugin'
import './styles/starhe/StarhePlugin.css'

function mountApp(): void {
  ReactDOM.createRoot(document.getElementById('root')!).render(
    <React.StrictMode>
      <StarhePlugin />
    </React.StrictMode>,
  );
}

// Inject apiBase from the best available source.
// In an iframe served from http://localhost:8082, window.location.origin
// is already the correct API base, so no postMessage handshake is needed.
function resolveApiBase(): string {
  if ((window as any).electronAPI?.apiBase) return (window as any).electronAPI.apiBase;
  if ((window as any).__STARHE_API_BASE__) return (window as any).__STARHE_API_BASE__;
  // Works correctly in both iframe (origin = server) and standalone dev (vite proxy)
  return window.location.origin;
}

(window as any).__STARHE_API_BASE__ = resolveApiBase();

// Notify parent MEDomics if running in an iframe (for compatibility)
if (window.parent !== window) {
  window.parent.postMessage({ type: 'STARHE_READY' }, '*');
}

// Listen for STARHE_INIT in case the parent wants to override apiBase later
window.addEventListener('message', (e: MessageEvent) => {
  if (e.data?.type !== 'STARHE_INIT' && e.data?.type !== 'PLUGIN_INIT') return;
  if (e.data.apiBase) (window as any).__STARHE_API_BASE__ = e.data.apiBase;
});

mountApp();
