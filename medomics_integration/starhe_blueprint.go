// starhe_blueprint.go — MEDomics blueprint for the STARHE plugin
//
// Architecture: reverse proxy
// ─────────────────────────────────────────────────────────────────────────────
// All requests to /starhe/* in the MEDomics Go server are forwarded
// (proxied) to the standalone STARHE Go server running on
// STARHE_SERVER_PORT (default: 8082).
//
// This avoids any protocol conflict:
//   - Our React app (iframe) talks directly to the MEDomics server (port
//     injected via postMessage from starhe.jsx).
//   - The MEDomics server redirects /starhe/* to our standalone server.
//   - Our standalone server handles DICOM, SSE, MongoDB cache, etc.
//
// ── Installation into MEDomics ──────────────────────────────────────────────
//
//  1. Copy this file to:
//       MEDomics/go_server/blueprints/starhe/starhe.go
//
//  2. In MEDomics/go_server/main.go, add:
//       import Starhe "go_module/blueprints/starhe"
//       // In the initialization function:
//       Starhe.AddHandleFunc()
//
//  3. Make sure the standalone STARHE Go server is started before
//     the plugin is opened (see starhe_server_launcher.js).
//
// ── Environment variables ────────────────────────────────────────────────────
//   STARHE_SERVER_PORT  Port of the standalone STARHE server (default: 8082)
package starhe

import (
	"log"
	"net/http"
	"net/http/httputil"
	"net/url"
	"os"
	"time"
)

// starheServerURL is the address of the standalone STARHE Go server.
func starheServerURL() string {
	port := os.Getenv("STARHE_SERVER_PORT")
	if port == "" {
		port = "8082"
	}
	return "http://localhost:" + port
}

// AddHandleFunc registers a reverse proxy /starhe/* → standalone STARHE server.
func AddHandleFunc() {
	target, err := url.Parse(starheServerURL())
	if err != nil {
		log.Fatalf("STARHE: URL invalide — %v", err)
	}

	proxy := &httputil.ReverseProxy{
		Director: func(req *http.Request) {
			req.URL.Scheme = target.Scheme
			req.URL.Host = target.Host
			req.Host = target.Host
			// Remove headers that cause issues behind a proxy
			req.Header.Del("X-Forwarded-For")
		},
		// Short FlushInterval so SSE (analysis stream) works
		// without proxy-side buffering.
		FlushInterval: 50 * time.Millisecond,
		ErrorHandler: func(w http.ResponseWriter, r *http.Request, err error) {
			log.Printf("STARHE proxy error: %v", err)
			http.Error(w, `{"error":"STARHE server unavailable"}`, http.StatusBadGateway)
		},
	}

	http.HandleFunc("/starhe/", func(w http.ResponseWriter, r *http.Request) {
		// CORS — required if the frontend is loaded from file:// or a
		// different domain (iframe in prod mode).
		w.Header().Set("Access-Control-Allow-Origin", "*")
		w.Header().Set("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
		w.Header().Set("Access-Control-Allow-Headers", "Content-Type")
		if r.Method == http.MethodOptions {
			w.WriteHeader(http.StatusNoContent)
			return
		}
		proxy.ServeHTTP(w, r)
	})

	log.Printf("STARHE: proxy /starhe/* → %s", starheServerURL())
}
