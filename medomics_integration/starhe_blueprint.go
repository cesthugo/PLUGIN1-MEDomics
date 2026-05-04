// starhe_blueprint.go — Blueprint MEDomics pour le plugin STARHE
//
// Architecture : reverse proxy
// ─────────────────────────────────────────────────────────────────────────────
// Toutes les requêtes vers /starhe/* dans le serveur Go MEDomics sont
// transmises (proxifiées) au serveur Go STARHE standalone qui tourne sur
// STARHE_SERVER_PORT (défaut : 8082).
//
// Cela évite tout conflit de protocole :
//   - Notre React app (iframe) parle directement au serveur MEDomics (port
//     injecté via postMessage depuis starhe.jsx).
//   - Le serveur MEDomics redirige /starhe/* vers notre serveur standalone.
//   - Notre serveur standalone gère DICOM, SSE, cache MongoDB, etc.
//
// ── Installation dans MEDomics ──────────────────────────────────────────────
//
//  1. Copier ce fichier dans :
//       MEDomics/go_server/blueprints/starhe/starhe.go
//
//  2. Dans MEDomics/go_server/main.go, ajouter :
//       import Starhe "go_module/blueprints/starhe"
//       // Dans la fonction d'initialisation :
//       Starhe.AddHandleFunc()
//
//  3. S'assurer que le serveur Go STARHE standalone est démarré avant
//     l'ouverture du plugin (voir starhe_server_launcher.js).
//
// ── Variables d'environnement ────────────────────────────────────────────────
//   STARHE_SERVER_PORT  Port du serveur STARHE standalone (défaut : 8082)
package starhe

import (
	"log"
	"net/http"
	"net/http/httputil"
	"net/url"
	"os"
	"time"
)

// starheServerURL est l'adresse du serveur Go STARHE standalone.
func starheServerURL() string {
	port := os.Getenv("STARHE_SERVER_PORT")
	if port == "" {
		port = "8082"
	}
	return "http://localhost:" + port
}

// AddHandleFunc enregistre un reverse proxy /starhe/* → serveur STARHE standalone.
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
			// Supprimer les en-têtes qui posent problème derrière un proxy
			req.Header.Del("X-Forwarded-For")
		},
		// FlushInterval court pour que le SSE (stream d'analyse) fonctionne
		// sans mise en tampon côté proxy.
		FlushInterval: 50 * time.Millisecond,
		ErrorHandler: func(w http.ResponseWriter, r *http.Request, err error) {
			log.Printf("STARHE proxy error: %v", err)
			http.Error(w, `{"error":"STARHE server unavailable"}`, http.StatusBadGateway)
		},
	}

	http.HandleFunc("/starhe/", func(w http.ResponseWriter, r *http.Request) {
		// CORS — nécessaire si le frontend est chargé depuis file:// ou un
		// domaine différent (iframe en mode prod).
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
