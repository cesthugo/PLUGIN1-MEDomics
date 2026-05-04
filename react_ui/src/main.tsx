import React from 'react'
import ReactDOM from 'react-dom/client'
import { StarhePlugin } from './StarhePlugin'
import './StarhePlugin/StarhePlugin.css'

function mountApp(): void {
  ReactDOM.createRoot(document.getElementById('root')!).render(
    <React.StrictMode>
      <StarhePlugin />
    </React.StrictMode>,
  );
}

// ── Initialisation selon le contexte de lancement ────────────────────────────
//
// 1. Electron standalone : window.electronAPI.apiBase est déjà disponible,
//    on monte immédiatement.
// 2. Iframe MEDomics : on attend un postMessage STARHE_INIT du parent qui
//    injecte { apiBase: 'http://localhost:PORT' } avant de monter.
// 3. Navigateur standard (dev Vite) : montage immédiat, proxy relatif.

if (
  (window as any).electronAPI?.apiBase ||
  (window as any).__STARHE_API_BASE__
) {
  // Contexte Electron standalone ou injection déjà effectuée
  mountApp();
} else if (window.parent !== window) {
  // Contexte iframe (MEDomics) : signaler qu'on est prêt et attendre le port.
  // On garde le listener actif même après le mount de fallback, car STARHE_INIT
  // peut arriver après que le port MEDomics soit devenu disponible.
  let mounted = false;

  const handleInit = (e: MessageEvent) => {
    if (e.data?.type !== 'STARHE_INIT') return;
    if (e.data.apiBase) {
      (window as any).__STARHE_API_BASE__ = e.data.apiBase;
    }
    if (!mounted) {
      mounted = true;
      mountApp();
    }
    // Si déjà monté, l'app relit getApiBase() au prochain appel → OK
  };

  window.addEventListener('message', handleInit);

  // Fallback : monter au bout de 3 s si STARHE_INIT n'arrive toujours pas
  setTimeout(() => {
    if (!mounted) {
      mounted = true;
      mountApp();
    }
  }, 3000);

  // Signaler au parent MEDomics que l'iframe est chargée et prête
  window.parent.postMessage({ type: 'STARHE_READY' }, '*');
} else {
  // Navigateur standard (dev ou embed direct)
  mountApp();
}
