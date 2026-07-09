/**
 * starhe.jsx — MEDomics page for the STARHE plugin
 *
 * Loads the STARHE frontend (React/Vite) into an iframe and injects into it
 * the base URL of the MEDomics Go server via postMessage (STARHE_INIT protocol).
 * The MEDomics server then proxies the /starhe/* routes to our
 * standalone STARHE Go server (see starhe_blueprint.go).
 *
 * ── Installation into MEDomics ──────────────────────────────────────────────
 *
 * 1. Copy this file to:
 *       MEDomics/renderer/components/mainPages/starhe.jsx
 *
 * 2. Copy the plugin's React build to:
 *       MEDomics/renderer/public/starhe-ui/   (copy the contents of renderer/dist/)
 *
 * 3. In renderer/components/layout/layoutManager.jsx:
 *       import StarhePage from '../mainPages/starhe'
 *       // Add to the renderContentComponent switch:
 *       case "starhe": return <StarhePage pageId={pageId} />
 *
 * 4. In renderer/components/layout/iconSidebar.jsx:
 *       // Add a Nav.Link with dispatchLayout({ type: "openStarhe" })
 *
 * 5. In renderer/components/layout/layoutContext.jsx:
 *       // Add the "openStarhe" case in the dispatchLayout reducer
 */

import { useContext, useEffect, useRef, useState } from 'react'
import { WorkspaceContext } from '../workspace/workspaceContext'

const StarhePage = () => {
  const { port } = useContext(WorkspaceContext)
  const iframeRef = useRef(null)
  const [loading, setLoading] = useState(true)

  // When the iframe signals that it is ready (STARHE_READY),
  // inject the base URL of the MEDomics Go server (which proxies to STARHE).
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

  // Dev: points to the plugin's Vite server (cd renderer && npm run dev)
  // Prod: points to the build copied into renderer/public/starhe-ui/
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
