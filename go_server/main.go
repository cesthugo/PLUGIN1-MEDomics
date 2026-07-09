// main.go — Entry point of the STARHE Go server
//
// Exposes 6 REST endpoints:
//
//	POST   /starhe/analyze        → Launches pipeline.py (SSE streaming)
//	GET    /starhe/results        → Lists MongoDB results
//	GET    /starhe/results/{id}   → Fetches a result by ID
//	DELETE /starhe/results/{id}   → Deletes a result
//	POST   /starhe/dicom/load     → Loads a DICOM and returns the frames as base64 JPEG
//	DELETE /starhe/cache          → Deletes a file's MongoDB cache (?path=…)
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

// mongoClient is the shared MongoDB client (connection pool).
var mongoClient *mongo.Client

func main() {
	runStartupCheck()
	initMongo()
	defer func() {
		ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		mongoClient.Disconnect(ctx) //nolint:errcheck
	}()

	mux := http.NewServeMux()
	mux.HandleFunc("GET /health", healthHandler)
	mux.Handle("/ui/", http.StripPrefix("/ui/", http.FileServer(http.Dir(cfg.UIDir))))
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

// initMongo initializes the MongoDB connection pool at startup.
// If the database is unreachable, the server still starts but the
// CRUD endpoints will return 503.
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

// withCORS adds the CORS headers and handles OPTIONS requests.
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
