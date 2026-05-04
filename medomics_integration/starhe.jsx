/**
 * starhe.jsx — Page MEDomics pour le plugin STARHE
 *
 * Charge le frontend STARHE (React/Vite) dans un iframe et lui injecte
 * la base URL du serveur Go MEDomics via postMessage (protocol STARHE_INIT).
 * Le serveur MEDomics proxifie ensuite les routes /starhe/* vers notre
 * serveur Go STARHE standalone (voir starhe_blueprint.go).
 *
 * ── Installation dans MEDomics ──────────────────────────────────────────────
 *
 * 1. Copier ce fichier dans :
 *       MEDomics/renderer/components/mainPages/starhe.jsx
 *
 * 2. Copier le build React du plugin dans :
 *       MEDomics/renderer/public/starhe-ui/   (copier le contenu de react_ui/dist/)
 *
 * 3. Dans renderer/components/layout/layoutManager.jsx :
 *       import StarhePage from '../mainPages/starhe'
 *       // Ajouter dans le switch renderContentComponent :
 *       case "starhe": return <StarhePage pageId={pageId} />
 *
 * 4. Dans renderer/components/layout/iconSidebar.jsx :
 *       // Ajouter un Nav.Link avec dispatchLayout({ type: "openStarhe" })
 *
 * 5. Dans renderer/components/layout/layoutContext.jsx :
 *       // Ajouter le case "openStarhe" dans le reducer dispatchLayout
 */

import { useContext, useEffect, useRef, useState } from 'react'
import { WorkspaceContext } from '../workspace/workspaceContext'

const StarhePage = () => {
  const { port } = useContext(WorkspaceContext)
  const iframeRef = useRef(null)
  const [loading, setLoading] = useState(true)

  // Quand l'iframe signale qu'elle est prête (STARHE_READY),
  // injecter la base URL du serveur Go MEDomics (qui proxifie vers STARHE).
  useEffect(() => {
    const handleMessage = (e) => {
      if (e.data?.type === 'STARHE_READY' && port && iframeRef.current) {
        iframeRef.current.contentWindow.postMessage(
          { type: 'STARHE_INIT', apiBase: `http://localhost:${port}` },
          '*',
        )
      }
    }
    window.addEventListener('message', handleMessage)
    return () => window.removeEventListener('message', handleMessage)
  }, [port])

  // Dev : pointe vers le serveur Vite du plugin (cd react_ui && npm run dev)
  // Prod : pointe vers le build copié dans renderer/public/starhe-ui/
  const starheUrl =
    process.env.NODE_ENV === 'development'
      ? 'http://localhost:5173'
      : '/starhe-ui/index.html'

  return (
    <div style={{ width: '100%', height: '100%', overflow: 'hidden', background: '#0c1018' }}>
      {loading && (
        <div
          style={{
            position: 'absolute',
            inset: 0,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: '#8b9dc3',
            fontSize: '14px',
          }}
        >
          Chargement du plugin STARHE…
        </div>
      )}
      <iframe
        ref={iframeRef}
        src={starheUrl}
        onLoad={() => setLoading(false)}
        style={{
          width: '100%',
          height: '100%',
          border: 'none',
          display: loading ? 'none' : 'block',
        }}
        title="STARHE Plugin"
        sandbox="allow-scripts allow-same-origin allow-forms"
      />
    </div>
  )
}

export default StarhePage
