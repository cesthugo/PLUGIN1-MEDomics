// main.go — Point d'entrée du serveur Go STARHE
//
// Expose 6 endpoints REST :
//
//	POST   /starhe/analyze        → Lance pipeline.py (SSE streaming)
//	GET    /starhe/results        → Liste les résultats MongoDB
//	GET    /starhe/results/{id}   → Récupère un résultat par ID
//	DELETE /starhe/results/{id}   → Supprime un résultat
//	POST   /starhe/dicom/load     → Charge un DICOM et retourne les frames en JPEG base64
//	DELETE /starhe/cache          → Supprime le cache MongoDB d'un fichier (?path=…)
//	GET    /health                → Healthcheck
package main

import (
	"context"
	"log"
	"net/http"
	"time"

	"go.mongodb.org/mongo-driver/mongo"
	"go.mongodb.org/mongo-driver/mongo/options"
)

// mongoClient est le client MongoDB partagé (connection pool).
var mongoClient *mongo.Client

func main() {
	initMongo()
	defer func() {
		ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		mongoClient.Disconnect(ctx) //nolint:errcheck
	}()

	mux := http.NewServeMux()
	mux.HandleFunc("GET /health", healthHandler)
	mux.HandleFunc("POST /starhe/analyze", analyzeHandler)
	mux.HandleFunc("POST /starhe/live", liveHandler)
	mux.HandleFunc("GET /starhe/results", listResultsHandler)
	mux.HandleFunc("GET /starhe/results/{id}", getResultHandler)
	mux.HandleFunc("DELETE /starhe/results/{id}", deleteResultHandler)
	mux.HandleFunc("POST /starhe/dicom/load", dicomLoadHandler)
	mux.HandleFunc("POST /starhe/mp4/load", mp4LoadHandler)
	mux.HandleFunc("POST /starhe/mp4/analyze", mp4AnalyzeHandler)
	mux.HandleFunc("DELETE /starhe/cache", deleteCacheHandler)

	addr := ":" + cfg.Port
	log.Printf("STARHE Go server → http://localhost%s", addr)
	log.Fatal(http.ListenAndServe(addr, withCORS(mux)))
}

// initMongo initialise le pool de connexions MongoDB au démarrage.
// Si la base est inaccessible, le serveur démarre quand même mais les
// endpoints CRUD retourneront 503.
func initMongo() {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	var err error
	mongoClient, err = mongo.Connect(ctx, options.Client().ApplyURI(cfg.MongoURI))
	if err != nil {
		log.Fatalf("MongoDB: connexion impossible — %v", err)
	}
	if err = mongoClient.Ping(ctx, nil); err != nil {
		log.Printf("MongoDB: ping échoué (%v) — les endpoints CRUD seront en 503", err)
	} else {
		log.Printf("MongoDB: connecté (%s / %s)", cfg.MongoURI, cfg.MongoDatabase)
	}
}

// withCORS ajoute les en-têtes CORS et gère les requêtes OPTIONS.
func withCORS(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Access-Control-Allow-Origin", "*")
		w.Header().Set("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
		w.Header().Set("Access-Control-Allow-Headers", "Content-Type")
		if r.Method == http.MethodOptions {
			w.WriteHeader(http.StatusNoContent)
			return
		}
		next.ServeHTTP(w, r)
	})
}

func healthHandler(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	w.Write([]byte(`{"status":"ok"}`)) //nolint:errcheck
}
