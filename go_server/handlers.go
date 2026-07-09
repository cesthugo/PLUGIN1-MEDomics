// handlers.go — HTTP handlers of the STARHE server
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

// analyzeRequest represents the body of the POST /starhe/analyze request.
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

// writeJSON serializes v to JSON and sends it with the given HTTP status code.
func writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	json.NewEncoder(w).Encode(v) //nolint:errcheck
}

// writeSSE sends an SSE event (format: "data: <payload>\n\n").
func writeSSE(w http.ResponseWriter, f http.Flusher, payload string) {
	fmt.Fprintf(w, "data: %s\n\n", payload)
	f.Flush()
}

// computeAnalysisMode computes the analysis_mode cache key from the request.
// Must match exactly the value computed by pipeline.py.
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

// findCachedResult looks up a cached result in MongoDB.
// Returns nil, nil if no document was found.
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

// streamCachedResult replays a cached result as SSE events.
func streamCachedResult(w http.ResponseWriter, f http.Flusher, doc bson.M) {
	// Progress event to inform the client
	progress, _ := json.Marshal(map[string]any{
		"level":   "progress",
		"message": "Résultats chargés depuis le cache MongoDB",
		"data":    map[string]any{"step": 1, "total": 1, "percent": 100},
	})
	writeSSE(w, f, string(progress))

	// Rebuild the result payload identical to the one emitted by pipeline.py
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

// collection returns the MongoDB collection of STARHE results.
func collection() *mongo.Collection {
	return mongoClient.Database(cfg.MongoDatabase).Collection(cfg.MongoCollection)
}

// ── POST /starhe/analyze ───────────────────────────────────────────────────
//
// Launches pipeline.py as a subprocess and streams its output as SSE.
//
// Each SSE event corresponds to a GO_PRINT line emitted by Python:
//
//	data: {"level":"progress","message":"Chargement DICOM…","data":{"step":1,"total":6,"percent":16}}
//	data: {"level":"result","message":"Pipeline completed","data":{...}}
//	data: [DONE]
func analyzeHandler(w http.ResponseWriter, r *http.Request) {
	// Default values + JSON decoding
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

	// Basic validation
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

	// SSE headers
	w.Header().Set("Content-Type", "text/event-stream")
	w.Header().Set("Cache-Control", "no-cache")
	w.Header().Set("Connection", "keep-alive")

	flusher, ok := w.(http.Flusher)
	if !ok {
		http.Error(w, `{"error":"streaming non supporté"}`, http.StatusInternalServerError)
		return
	}

	// Check the MongoDB cache before launching Python
	analysisMode := computeAnalysisMode(req)
	if cached, err := findCachedResult(r.Context(), req.DicomPath, analysisMode); err != nil {
		log.Printf("avertissement cache MongoDB: %v", err)
	} else if cached != nil {
		log.Printf("cache hit: %s [%s]", req.DicomPath, analysisMode)
		streamCachedResult(w, flusher, cached)
		return
	}

	// Build the subprocess arguments
	args := []string{
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

	cmd := pythonCmd(r.Context(), "pipeline", args...)

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

	// Consume stderr in a goroutine to avoid blocking the OS buffer
	go func() { io.Copy(log.Writer(), stderr) }() //nolint:errcheck

	// Read stdout line by line and forward each GO_PRINT as SSE.
	// The final result (go_result) can exceed 64 KB (many detections):
	// allocate a 10 MB buffer to avoid a pipe deadlock.
	scanner := bufio.NewScanner(stdout)
	scanner.Buffer(make([]byte, 0, 1024*1024), 10*1024*1024)
	for scanner.Scan() {
		line := scanner.Text()
		if !strings.HasPrefix(line, "GO_PRINT|") {
			continue
		}
		// Format: "GO_PRINT|<level>|<json_payload>"
		parts := strings.SplitN(line, "|", 3)
		if len(parts) == 3 {
			writeSSE(w, flusher, parts[2])
		}
	}

	finishSSE(w, flusher, cmd.Wait(), r.Context().Err(), "pipeline Python")
}

// sseError sends an SSE error event followed by [DONE].
func sseError(w http.ResponseWriter, f http.Flusher, msg string) {
	payload, _ := json.Marshal(map[string]string{"level": "error", "message": msg})
	writeSSE(w, f, string(payload))
	writeSSE(w, f, "[DONE]")
}

// finishSSE closes an SSE stream after cmd.Wait(): if the Python subprocess
// exited with an error (and the client did not cancel the request), a
// {"level":"error"} event is emitted BEFORE [DONE] so the frontend can
// distinguish success from a crash — otherwise the UI would show ✓ "done"
// with Risk: — even though the models never ran.
func finishSSE(w http.ResponseWriter, f http.Flusher, waitErr error, ctxErr error, what string) {
	if waitErr != nil && ctxErr == nil {
		log.Printf("%s terminé avec erreur: %v", what, waitErr)
		exitCode := -1
		if ee, ok := waitErr.(*exec.ExitError); ok {
			exitCode = ee.ExitCode()
		}
		payload, _ := json.Marshal(map[string]string{
			"level":   "error",
			"message": fmt.Sprintf("pipeline exit code %d — consultez les logs serveur (%s)", exitCode, what),
		})
		writeSSE(w, f, string(payload))
	}
	writeSSE(w, f, "[DONE]")
}

// ── POST /starhe/live ──────────────────────────────────────────────────────
//
// Launches run_live.py as a subprocess and streams its output as SSE.
// The subprocess runs until the client disconnects (HTTP context
// cancelled → exec.CommandContext kills the process).
//
// JSON request body:
//
//	{
//	  "source":      "cstore" | "folder" | "hdmi",
//	  "port":        11112,          // C-STORE SCP port (source=cstore)
//	  "folder_path": "/path/...",    // folder to watch (source=folder)
//	  "device":      0,              // cv2 index (source=hdmi)
//	  "no_risk":     false           // disable STARHE-RISK
//	}
type liveRequest struct {
	Source     string `json:"source"`
	Port       int    `json:"port"`
	FolderPath string `json:"folder_path"`
	Device     int    `json:"device"`
	NoRisk     bool   `json:"no_risk"`
}

func liveHandler(w http.ResponseWriter, r *http.Request) {
	req := liveRequest{
		Source: "folder",
		Port:   11112,
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, `{"error":"corps de requête invalide"}`, http.StatusBadRequest)
		return
	}

	switch req.Source {
	case "cstore", "folder", "hdmi":
		// valid
	default:
		http.Error(w, `{"error":"source invalide (cstore|folder|hdmi)"}`, http.StatusBadRequest)
		return
	}
	if req.Source == "folder" && req.FolderPath == "" {
		http.Error(w, `{"error":"folder_path est requis pour source=folder"}`, http.StatusBadRequest)
		return
	}

	// SSE headers
	w.Header().Set("Content-Type", "text/event-stream")
	w.Header().Set("Cache-Control", "no-cache")
	w.Header().Set("Connection", "keep-alive")

	flusher, ok := w.(http.Flusher)
	if !ok {
		http.Error(w, `{"error":"streaming non supporté"}`, http.StatusInternalServerError)
		return
	}

	// Build the subprocess arguments
	args := []string{
		"--source", req.Source,
	}
	switch req.Source {
	case "cstore":
		args = append(args, "--port", strconv.Itoa(req.Port))
	case "folder":
		args = append(args, "--folder", req.FolderPath)
	case "hdmi":
		args = append(args, "--device", strconv.Itoa(req.Device))
	}
	if req.NoRisk {
		args = append(args, "--no_risk")
	}

	cmd := pythonCmd(r.Context(), "ai.run_live", args...)

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

	go func() { io.Copy(log.Writer(), stderr) }() //nolint:errcheck

	// Read stdout line by line; each GO_PRINT is forwarded as SSE.
	// Base64 JPEG frames can exceed 64 KB — 10 MB buffer.
	scanner := bufio.NewScanner(stdout)
	scanner.Buffer(make([]byte, 0, 1024*1024), 10*1024*1024)
	for scanner.Scan() {
		line := scanner.Text()
		if !strings.HasPrefix(line, "GO_PRINT|") {
			continue
		}
		parts := strings.SplitN(line, "|", 3)
		if len(parts) == 3 {
			writeSSE(w, flusher, parts[2])
		}
	}

	finishSSE(w, flusher, cmd.Wait(), r.Context().Err(), "pipeline live")
}

// ── GET /starhe/results ────────────────────────────────────────────────────
//
// Optional parameter: ?limit=N (default 50, max 1000).
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

	// Convert ObjectIDs to JSON-readable strings
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
