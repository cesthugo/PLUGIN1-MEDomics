// handlers_mp4.go — Endpoints STARHE pour le chargement et l'analyse de fichiers MP4
//
// POST /starhe/mp4/load    → charge un MP4 via Python et retourne les frames en JPEG base64
//   Accept uniquement multipart/form-data (upload navigateur)
//
// POST /starhe/mp4/analyze → analyse un MP4 (pipeline sans DICOM) via Python, stream SSE
package main

import (
	"bufio"
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"time"
)

// ── POST /starhe/mp4/load ──────────────────────────────────────────────────
//
// Accepte deux modes :
//   1. multipart/form-data : champ "file" (.mp4), "quality" (int), "max_dim" (int)
//   2. application/json   : {"mp4_path": "/tmp/starhe_mp4_<hash>.mp4", "quality": 70, "max_dim": 640}
//      (pour recharger un fichier temporaire déjà présent sur le serveur)
//
// Réponse : JSON retourné par loader_mp4_cli.py (même format que loader_cli.py)
// avec "server_path" injecté pour que le client sache quel chemin envoyer à /starhe/mp4/analyze.
func mp4LoadHandler(w http.ResponseWriter, r *http.Request) {
	quality := 70
	maxDim  := 640
	var tmpPath  string
	var fileName string

	ct := r.Header.Get("Content-Type")
	if strings.Contains(ct, "application/json") {
		// ── Mode JSON : chemin absolu d'un fichier temporaire déjà présent ──
		var body struct {
			Mp4Path string `json:"mp4_path"`
			Quality int    `json:"quality"`
			MaxDim  int    `json:"max_dim"`
		}
		if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
			writeJSON(w, http.StatusBadRequest, map[string]string{
				"error": "JSON invalide : " + err.Error(),
			})
			return
		}
		if body.Mp4Path == "" {
			writeJSON(w, http.StatusBadRequest, map[string]string{
				"error": "champ 'mp4_path' manquant",
			})
			return
		}
		// Sécurité : on n'accepte que les fichiers que nous avons créés nous-mêmes
		cleanPath := filepath.Clean(body.Mp4Path)
		base := filepath.Base(cleanPath)
		tmpDir := filepath.Clean(os.TempDir())
		if !strings.HasPrefix(base, "starhe_mp4_") || !strings.HasPrefix(cleanPath, tmpDir) {
			writeJSON(w, http.StatusForbidden, map[string]string{
				"error": "chemin non autorisé",
			})
			return
		}
		if _, statErr := os.Stat(cleanPath); statErr != nil {
			writeJSON(w, http.StatusNotFound, map[string]string{
				"error": "fichier introuvable : " + cleanPath,
			})
			return
		}
		tmpPath  = cleanPath
		fileName = base
		if body.Quality >= 1 && body.Quality <= 95 { quality = body.Quality }
		if body.MaxDim  >= 64 && body.MaxDim  <= 4096 { maxDim = body.MaxDim   }
	} else {
		// ── Mode multipart : upload depuis le navigateur ──────────────────
		// Limite à 500 MB (vidéos mp4 peuvent être volumineuses)
		if err := r.ParseMultipartForm(500 << 20); err != nil {
			writeJSON(w, http.StatusBadRequest, map[string]string{
				"error": "impossible de parser le formulaire : " + err.Error(),
			})
			return
		}

		f, header, err := r.FormFile("file")
		if err != nil {
			writeJSON(w, http.StatusBadRequest, map[string]string{
				"error": "champ 'file' manquant dans le formulaire",
			})
			return
		}
		defer f.Close()

		// Paramètres optionnels
		if v := r.FormValue("quality"); v != "" {
			if n, errV := strconv.Atoi(v); errV == nil { quality = n }
		}
		if v := r.FormValue("max_dim"); v != "" {
			if n, errV := strconv.Atoi(v); errV == nil { maxDim = n }
		}
		if quality < 1 || quality > 95  { quality = 70  }
		if maxDim  < 64 || maxDim > 4096 { maxDim = 640 }

		// Lit le contenu pour calculer le hash SHA-256 (même contenu → même chemin)
		fileBytes, err := io.ReadAll(f)
		if err != nil {
			writeJSON(w, http.StatusInternalServerError, map[string]string{
				"error": "erreur lecture fichier uploadé : " + err.Error(),
			})
			return
		}

		hash := sha256.Sum256(fileBytes)
		hashStr := hex.EncodeToString(hash[:])[:24]
		tmpPath  = filepath.Join(os.TempDir(), "starhe_mp4_"+hashStr+".mp4")
		fileName = header.Filename

		if _, statErr := os.Stat(tmpPath); os.IsNotExist(statErr) {
			if err := os.WriteFile(tmpPath, fileBytes, 0600); err != nil {
				writeJSON(w, http.StatusInternalServerError, map[string]string{
					"error": "erreur écriture fichier temporaire : " + err.Error(),
				})
				return
			}
		}
	} // end multipart else

	// Timeout généreux : 120 s pour les vidéos longues
	ctx, cancel := context.WithTimeout(r.Context(), 120*time.Second)
	defer cancel()

	args := []string{
		"-m", "starhe_plugin.dicom.loader_mp4_cli",
		tmpPath,
		"--quality", strconv.Itoa(quality),
		"--max-dim", strconv.Itoa(maxDim),
	}

	cmd := exec.CommandContext(ctx, cfg.PythonExe, args...)
	cmd.Dir = cfg.PythonModPath
	cmd.Env = append(os.Environ(),
		"PYTHONPATH="+cfg.PythonModPath,
		"PYTHONUTF8=1",
	)

	var stderr bytes.Buffer
	cmd.Stderr = &stderr

	out, err := cmd.Output()
	if err != nil {
		os.Remove(tmpPath)
		errResp := map[string]string{
			"error":  "subprocess Python échoué : " + err.Error(),
			"stderr": stderr.String(),
		}
		if len(out) > 0 {
			errResp["stdout"] = string(out)
			var pyErr map[string]string
			if jsonErr := json.Unmarshal(out, &pyErr); jsonErr == nil {
				if msg, ok := pyErr["error"]; ok {
					errResp["python_error"] = msg
				}
				if tb, ok := pyErr["traceback"]; ok {
					errResp["python_traceback"] = tb
				}
			}
		}
		writeJSON(w, http.StatusInternalServerError, errResp)
		return
	}

	// Injecte server_path et le nom de fichier original dans la réponse
	var obj map[string]interface{}
	if err := json.Unmarshal(out, &obj); err == nil {
		obj["server_path"] = tmpPath
		if fileName != "" {
			obj["file_name"] = fileName
		}
		if patched, err := json.Marshal(obj); err == nil {
			out = patched
		}
	}

	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(http.StatusOK)
	w.Write(out) //nolint:errcheck
}

// mp4AnalyzeRequest représente le corps de la requête POST /starhe/mp4/analyze.
type mp4AnalyzeRequest struct {
	Mp4Path            string `json:"mp4_path"`
	RunRisk            bool   `json:"run_risk"`
	RunDetection       bool   `json:"run_detection"`
	BackScanConversion bool   `json:"back_scan_conversion"`
	BackscanWidth      int    `json:"backscan_width"`
	BackscanHeight     int    `json:"backscan_height"`
}

// computeAnalysisModeMp4 calcule la clé de cache analysis_mode pour un fichier MP4.
// Inclut source=mp4 pour distinguer des analyses DICOM sur le même file_path.
func computeAnalysisModeMp4(req mp4AnalyzeRequest) string {
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
	return fmt.Sprintf("risk=%s,detect=%s,backscan=%s,anon=none,source=mp4", r, d, b)
}

// ── POST /starhe/mp4/analyze ───────────────────────────────────────────────
//
// Lance pipeline_mp4.py en subprocess et streame la sortie au format SSE.
//
// Corps de requête JSON :
//
//	{
//	  "mp4_path":            "/tmp/starhe_mp4_<hash>.mp4",
//	  "run_risk":            true,
//	  "run_detection":       true,
//	  "back_scan_conversion":true,
//	  "backscan_width":      512,
//	  "backscan_height":     512
//	}
func mp4AnalyzeHandler(w http.ResponseWriter, r *http.Request) {
	req := mp4AnalyzeRequest{
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

	if req.Mp4Path == "" {
		http.Error(w, `{"error":"mp4_path est requis"}`, http.StatusBadRequest)
		return
	}
	if _, err := os.Stat(req.Mp4Path); err != nil {
		http.Error(w, `{"error":"fichier mp4_path introuvable"}`, http.StatusBadRequest)
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

	// Vérification du cache MongoDB
	analysisMode := computeAnalysisModeMp4(req)
	if cached, err := findCachedResult(r.Context(), req.Mp4Path, analysisMode); err != nil {
		log.Printf("avertissement cache MongoDB (mp4): %v", err)
	} else if cached != nil {
		log.Printf("cache hit mp4: %s [%s]", req.Mp4Path, analysisMode)
		streamCachedResult(w, flusher, cached)
		return
	}

	// Construction des arguments subprocess
	args := []string{
		"-m", "starhe_plugin.pipeline_mp4",
		req.Mp4Path,
		"--backscan_width",  strconv.Itoa(req.BackscanWidth),
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
		"PYTHONUTF8=1",
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

	go func() { io.Copy(log.Writer(), stderr) }() //nolint:errcheck

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

	if err := cmd.Wait(); err != nil && r.Context().Err() == nil {
		log.Printf("pipeline_mp4 Python terminé avec erreur: %v", err)
	}

	writeSSE(w, flusher, "[DONE]")
}
