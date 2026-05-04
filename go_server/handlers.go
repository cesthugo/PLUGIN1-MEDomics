// handlers.go — Handlers HTTP du serveur STARHE
package main

import (
	"bufio"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"os/exec"
	"strconv"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/bson"
	"go.mongodb.org/mongo-driver/bson/primitive"
	"go.mongodb.org/mongo-driver/mongo"
	"go.mongodb.org/mongo-driver/mongo/options"
)

// ── Types ──────────────────────────────────────────────────────────────────

// analyzeRequest représente le corps de la requête POST /starhe/analyze.
type analyzeRequest struct {
	DicomPath          string `json:"dicom_path"`
	AnonMode           string `json:"anon_mode"`
	RunRisk            bool   `json:"run_risk"`
	RunDetection       bool   `json:"run_detection"`
	BackScanConversion bool   `json:"back_scan_conversion"`
	BackscanWidth      int    `json:"backscan_width"`
	BackscanHeight     int    `json:"backscan_height"`
}

// ── Helpers ────────────────────────────────────────────────────────────────

// writeJSON sérialise v en JSON et l'envoie avec le code HTTP donné.
func writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	json.NewEncoder(w).Encode(v) //nolint:errcheck
}

// writeSSE envoie un événement SSE (format : "data: <payload>\n\n").
func writeSSE(w http.ResponseWriter, f http.Flusher, payload string) {
	fmt.Fprintf(w, "data: %s\n\n", payload)
	f.Flush()
}

// computeAnalysisMode calcule la clé de cache analysis_mode depuis la requête.
// Doit correspondre exactement à la valeur calculée par pipeline.py.
func computeAnalysisMode(req analyzeRequest) string {
	r := "0"
	if req.RunRisk {
		r = "1"
	}
	d := "0"
	if req.RunDetection {
		d = "1"
	}
	b := "0"
	if req.BackScanConversion {
		b = "1"
	}
	return fmt.Sprintf("risk=%s,detect=%s,backscan=%s,anon=%s", r, d, b, req.AnonMode)
}

// findCachedResult cherche un résultat en cache dans MongoDB.
// Retourne nil, nil si aucun document trouvé.
func findCachedResult(ctx context.Context, filePath, analysisMode string) (bson.M, error) {
	if mongoClient == nil {
		return nil, nil
	}
	ctx2, cancel := context.WithTimeout(ctx, 3*time.Second)
	defer cancel()
	var doc bson.M
	err := collection().FindOne(ctx2, bson.M{
		"file_path":     filePath,
		"analysis_mode": analysisMode,
	}).Decode(&doc)
	if err == mongo.ErrNoDocuments {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	return doc, nil
}

// streamCachedResult rejoue un résultat mis en cache comme événements SSE.
func streamCachedResult(w http.ResponseWriter, f http.Flusher, doc bson.M) {
	// Événement progress pour informer le client
	progress, _ := json.Marshal(map[string]any{
		"level":   "progress",
		"message": "Résultats chargés depuis le cache MongoDB",
		"data":    map[string]any{"step": 1, "total": 1, "percent": 100},
	})
	writeSSE(w, f, string(progress))

	// Reconstruit le payload résultat identique à celui émis par pipeline.py
	resultData := map[string]any{}
	if oid, ok := doc["_id"].(primitive.ObjectID); ok {
		resultData["doc_id"] = oid.Hex()
	}
	if v, ok := doc["num_frames"]; ok {
		resultData["num_frames"] = v
	}
	if v, ok := doc["roi"]; ok {
		resultData["roi"] = v
	}
	if v, ok := doc["detections_per_frame"]; ok {
		resultData["detections_per_frame"] = v
	}
	if v, ok := doc["risk"]; ok {
		resultData["risk"] = v
	}

	resultEvt, _ := json.Marshal(map[string]any{
		"level":   "result",
		"message": "Traitement terminé",
		"data":    resultData,
	})
	writeSSE(w, f, string(resultEvt))
	writeSSE(w, f, "[DONE]")
}

// collection retourne la collection MongoDB des résultats STARHE.
func collection() *mongo.Collection {
	return mongoClient.Database(cfg.MongoDatabase).Collection(cfg.MongoCollection)
}

// ── POST /starhe/analyze ───────────────────────────────────────────────────
//
// Lance pipeline.py en subprocess et streame sa sortie au format SSE.
//
// Chaque événement SSE correspond à une ligne GO_PRINT émise par Python :
//
//	data: {"level":"progress","message":"Chargement DICOM…","data":{"step":1,"total":6,"percent":16}}
//	data: {"level":"result","message":"Pipeline terminé","data":{...}}
//	data: [DONE]
func analyzeHandler(w http.ResponseWriter, r *http.Request) {
	// Valeurs par défaut + décodage JSON
	req := analyzeRequest{
		AnonMode:           "hash",
		RunRisk:            true,
		RunDetection:       true,
		BackScanConversion: true,
		BackscanWidth:      512,
		BackscanHeight:     512,
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, `{"error":"corps de requête invalide"}`, http.StatusBadRequest)
		return
	}

	// Validation de base
	if req.DicomPath == "" {
		http.Error(w, `{"error":"dicom_path est requis"}`, http.StatusBadRequest)
		return
	}
	if _, err := os.Stat(req.DicomPath); err != nil {
		http.Error(w, `{"error":"fichier dicom_path introuvable"}`, http.StatusBadRequest)
		return
	}
	if req.BackscanWidth < 64 || req.BackscanWidth > 2048 {
		req.BackscanWidth = 512
	}
	if req.BackscanHeight < 64 || req.BackscanHeight > 2048 {
		req.BackscanHeight = 512
	}

	// En-têtes SSE
	w.Header().Set("Content-Type", "text/event-stream")
	w.Header().Set("Cache-Control", "no-cache")
	w.Header().Set("Connection", "keep-alive")

	flusher, ok := w.(http.Flusher)
	if !ok {
		http.Error(w, `{"error":"streaming non supporté"}`, http.StatusInternalServerError)
		return
	}

	// Vérification du cache MongoDB avant de lancer Python
	analysisMode := computeAnalysisMode(req)
	if cached, err := findCachedResult(r.Context(), req.DicomPath, analysisMode); err != nil {
		log.Printf("avertissement cache MongoDB: %v", err)
	} else if cached != nil {
		log.Printf("cache hit: %s [%s]", req.DicomPath, analysisMode)
		streamCachedResult(w, flusher, cached)
		return
	}

	// Construction des arguments subprocess
	args := []string{
		"-m", "starhe_plugin.pipeline",
		req.DicomPath,
		"--anon_mode", req.AnonMode,
		"--backscan_width", strconv.Itoa(req.BackscanWidth),
		"--backscan_height", strconv.Itoa(req.BackscanHeight),
	}
	if !req.RunRisk {
		args = append(args, "--no_risk")
	}
	if !req.RunDetection {
		args = append(args, "--no_detection")
	}
	if !req.BackScanConversion {
		args = append(args, "--no_backscan")
	}
	args = append(args, "--analysis_mode", analysisMode)

	cmd := exec.CommandContext(r.Context(), cfg.PythonExe, args...)
	cmd.Dir = cfg.PythonModPath
	cmd.Env = append(os.Environ(),
		"PYTHONPATH="+cfg.PythonModPath,
		"PYTHONUTF8=1", // force UTF-8 sous Windows
	)

	stdout, err := cmd.StdoutPipe()
	if err != nil {
		sseError(w, flusher, "stdout pipe: "+err.Error())
		return
	}
	stderr, _ := cmd.StderrPipe()

	if err := cmd.Start(); err != nil {
		sseError(w, flusher, "démarrage Python échoué: "+err.Error())
		return
	}

	// Consomme stderr dans un goroutine pour éviter le blocage du buffer OS
	go func() { io.Copy(log.Writer(), stderr) }() //nolint:errcheck

	// Lit stdout ligne par ligne et forward chaque GO_PRINT en SSE
	// Le résultat final (go_result) peut dépasser 64 KB (beaucoup de détections) :
	// on alloue un buffer de 10 MB pour éviter le deadlock pipe.
	scanner := bufio.NewScanner(stdout)
	scanner.Buffer(make([]byte, 0, 1024*1024), 10*1024*1024)
	for scanner.Scan() {
		line := scanner.Text()
		if !strings.HasPrefix(line, "GO_PRINT|") {
			continue
		}
		// Format : "GO_PRINT|<level>|<json_payload>"
		parts := strings.SplitN(line, "|", 3)
		if len(parts) == 3 {
			writeSSE(w, flusher, parts[2])
		}
	}

	if err := cmd.Wait(); err != nil && r.Context().Err() == nil {
		// Erreur réelle (pas une déconnexion client)
		log.Printf("pipeline Python terminé avec erreur: %v", err)
	}

	writeSSE(w, flusher, "[DONE]")
}

// sseError envoie un événement SSE d'erreur puis [DONE].
func sseError(w http.ResponseWriter, f http.Flusher, msg string) {
	payload, _ := json.Marshal(map[string]string{"level": "error", "message": msg})
	writeSSE(w, f, string(payload))
	writeSSE(w, f, "[DONE]")
}

// ── POST /starhe/live ──────────────────────────────────────────────────────
// Stub — analyse en direct non implémentée dans cette version.
func liveNotImplementedHandler(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusNotImplemented)
	w.Write([]byte(`{"error":"Analyse en direct non disponible dans cette version du serveur."}`)) //nolint:errcheck
}

// ── GET /starhe/results ────────────────────────────────────────────────────
//
// Paramètre optionnel : ?limit=N (défaut 50, max 1000).
func listResultsHandler(w http.ResponseWriter, r *http.Request) {
	limit := int64(50)
	if l := r.URL.Query().Get("limit"); l != "" {
		if n, err := strconv.ParseInt(l, 10, 64); err == nil && n > 0 && n <= 1000 {
			limit = n
		}
	}

	ctx, cancel := context.WithTimeout(r.Context(), 5*time.Second)
	defer cancel()

	opts := options.Find().
		SetSort(bson.D{{Key: "processed_at", Value: -1}}).
		SetLimit(limit)

	cursor, err := collection().Find(ctx, bson.D{}, opts)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": err.Error()})
		return
	}
	defer cursor.Close(ctx)

	var results []bson.M
	if err := cursor.All(ctx, &results); err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": err.Error()})
		return
	}

	// Convertit les ObjectID en strings lisibles par JSON
	for _, doc := range results {
		if oid, ok := doc["_id"].(primitive.ObjectID); ok {
			doc["_id"] = oid.Hex()
		}
	}
	writeJSON(w, http.StatusOK, results)
}

// ── GET /starhe/results/{id} ───────────────────────────────────────────────

func getResultHandler(w http.ResponseWriter, r *http.Request) {
	oid, err := primitive.ObjectIDFromHex(r.PathValue("id"))
	if err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "id invalide"})
		return
	}

	ctx, cancel := context.WithTimeout(r.Context(), 5*time.Second)
	defer cancel()

	var doc bson.M
	if err := collection().FindOne(ctx, bson.M{"_id": oid}).Decode(&doc); err != nil {
		if err == mongo.ErrNoDocuments {
			writeJSON(w, http.StatusNotFound, map[string]string{"error": "document introuvable"})
		} else {
			writeJSON(w, http.StatusInternalServerError, map[string]string{"error": err.Error()})
		}
		return
	}
	if oid, ok := doc["_id"].(primitive.ObjectID); ok {
		doc["_id"] = oid.Hex()
	}
	writeJSON(w, http.StatusOK, doc)
}

// ── DELETE /starhe/results/{id} ────────────────────────────────────────────

func deleteResultHandler(w http.ResponseWriter, r *http.Request) {
	oid, err := primitive.ObjectIDFromHex(r.PathValue("id"))
	if err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "id invalide"})
		return
	}

	ctx, cancel := context.WithTimeout(r.Context(), 5*time.Second)
	defer cancel()

	res, err := collection().DeleteOne(ctx, bson.M{"_id": oid})
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": err.Error()})
		return
	}
	if res.DeletedCount == 0 {
		writeJSON(w, http.StatusNotFound, map[string]string{"error": "document introuvable"})
		return
	}
	writeJSON(w, http.StatusOK, map[string]bool{"deleted": true})
}
