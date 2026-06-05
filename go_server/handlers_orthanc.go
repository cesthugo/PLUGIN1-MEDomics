// handlers_orthanc.go — Proxy Orthanc PACS pour le navigateur DICOM STARHE
//
// Expose une API REST légère qui proxifie Orthanc (server-side pour éviter les
// contraintes CORS) et ajoute un endpoint de chargement qui télécharge un fichier
// DICOM depuis Orthanc puis le passe à loader_cli.py (identique au mode upload).
//
// Routes :
//
//	GET  /starhe/orthanc/status              → santé du serveur Orthanc
//	GET  /starhe/orthanc/patients            → liste des patients (expand)
//	GET  /starhe/orthanc/patients/{id}       → détails patient (études)
//	GET  /starhe/orthanc/studies/{id}        → détails étude (séries)
//	GET  /starhe/orthanc/series/{id}         → instances d'une série (expand)
//	GET  /starhe/orthanc/instances/{id}      → métadonnées d'une instance
//	POST /starhe/orthanc/load                → télécharge + charge dans le visualiseur
package main

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"time"
)

// orthancDo effectue une requête HTTP authentifiée vers Orthanc.
// Retourne (body, statusCode, error).
func orthancDo(ctx context.Context, method, path string, body io.Reader) ([]byte, int, error) {
	url := cfg.OrthancURL + path
	req, err := http.NewRequestWithContext(ctx, method, url, body)
	if err != nil {
		return nil, 0, err
	}
	if cfg.OrthancUser != "" {
		req.SetBasicAuth(cfg.OrthancUser, cfg.OrthancPassword)
	}
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return nil, 0, err
	}
	defer resp.Body.Close()
	respBody, err := io.ReadAll(resp.Body)
	return respBody, resp.StatusCode, err
}

// orthancProxy effectue un GET vers Orthanc et forwarde le résultat JSON tel quel.
func orthancProxy(w http.ResponseWriter, r *http.Request, orthancPath string) {
	ctx, cancel := context.WithTimeout(r.Context(), 20*time.Second)
	defer cancel()
	body, status, err := orthancDo(ctx, http.MethodGet, orthancPath, nil)
	if err != nil {
		writeJSON(w, http.StatusBadGateway, map[string]string{
			"error": "Orthanc inaccessible : " + err.Error(),
			"url":   cfg.OrthancURL,
		})
		return
	}
	if status != http.StatusOK {
		writeJSON(w, http.StatusBadGateway, map[string]string{
			"error": fmt.Sprintf("Orthanc a retourné HTTP %d pour %s", status, orthancPath),
		})
		return
	}
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	w.Write(body) //nolint:errcheck
}

// ── GET /starhe/orthanc/status ─────────────────────────────────────────────

func orthancStatusHandler(w http.ResponseWriter, r *http.Request) {
	ctx, cancel := context.WithTimeout(r.Context(), 5*time.Second)
	defer cancel()
	body, status, err := orthancDo(ctx, http.MethodGet, "/system", nil)
	if err != nil || status != http.StatusOK {
		msg := fmt.Sprintf("Orthanc inaccessible (HTTP %d)", status)
		if err != nil {
			msg = err.Error()
		}
		writeJSON(w, http.StatusServiceUnavailable, map[string]any{
			"available": false,
			"error":     msg,
			"url":       cfg.OrthancURL,
		})
		return
	}
	var system map[string]any
	json.Unmarshal(body, &system) //nolint:errcheck
	writeJSON(w, http.StatusOK, map[string]any{
		"available": true,
		"url":       cfg.OrthancURL,
		"system":    system,
	})
}

// ── GET /starhe/orthanc/patients ───────────────────────────────────────────
// Retourne le tableau complet des patients avec leurs MainDicomTags et la liste
// des Study IDs (?expand=true déclenche l'expansion côté Orthanc).

func orthancListPatientsHandler(w http.ResponseWriter, r *http.Request) {
	orthancProxy(w, r, "/patients?expand=true")
}

// ── GET /starhe/orthanc/patients/{id} ─────────────────────────────────────

func orthancPatientHandler(w http.ResponseWriter, r *http.Request) {
	orthancProxy(w, r, "/patients/"+r.PathValue("id"))
}

// ── GET /starhe/orthanc/studies/{id} ──────────────────────────────────────

func orthancStudyHandler(w http.ResponseWriter, r *http.Request) {
	orthancProxy(w, r, "/studies/"+r.PathValue("id"))
}

// ── GET /starhe/orthanc/series/{id} ───────────────────────────────────────
// Retourne les instances d'une série avec expand (MainDicomTags + NumberOfFrames).

func orthancSeriesInstancesHandler(w http.ResponseWriter, r *http.Request) {
	orthancProxy(w, r, "/series/"+r.PathValue("id")+"/instances?expand=true")
}

// ── GET /starhe/orthanc/instances/{id} ────────────────────────────────────

func orthancInstanceHandler(w http.ResponseWriter, r *http.Request) {
	orthancProxy(w, r, "/instances/"+r.PathValue("id"))
}

// ── POST /starhe/orthanc/load ──────────────────────────────────────────────
//
// Télécharge une instance DICOM depuis Orthanc, la sauvegarde dans un fichier
// temporaire déterministe (SHA-256), puis appelle loader_cli.py pour obtenir
// les frames en JPEG base64 — identique au mode upload multipart.
//
// Corps JSON :
//
//	{ "instance_id": "orthanc-uuid", "quality": 70, "max_dim": 640 }
//
// Réponse : même JSON que /starhe/dicom/load (frames_b64, métadonnées…)
// avec en plus le champ "server_path" pour utilisation par /starhe/analyze.
func orthancLoadHandler(w http.ResponseWriter, r *http.Request) {
	var req struct {
		InstanceID string `json:"instance_id"`
		Quality    int    `json:"quality"`
		MaxDim     int    `json:"max_dim"`
	}
	req.Quality = 70
	req.MaxDim = 640

	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{
			"error": "corps JSON invalide : " + err.Error(),
		})
		return
	}
	if req.InstanceID == "" {
		writeJSON(w, http.StatusBadRequest, map[string]string{
			"error": "instance_id est requis",
		})
		return
	}

	// ── 1. Télécharger le fichier DICOM brut depuis Orthanc ────────────────
	ctx, cancel := context.WithTimeout(r.Context(), 120*time.Second)
	defer cancel()

	dicomBytes, status, err := orthancDo(ctx, http.MethodGet,
		"/instances/"+req.InstanceID+"/file", nil)
	if err != nil || status != http.StatusOK {
		writeJSON(w, http.StatusBadGateway, map[string]string{
			"error": fmt.Sprintf(
				"impossible de télécharger l'instance Orthanc %s (HTTP %d, %v)",
				req.InstanceID, status, err),
		})
		return
	}

	// ── 2. Chemin temp déterministe (SHA-256 → cache hit si même contenu) ─
	hash := sha256.Sum256(dicomBytes)
	hashStr := hex.EncodeToString(hash[:])[:24]
	tmpPath := filepath.Join(os.TempDir(), "starhe_orthanc_"+hashStr+".dcm")

	if _, statErr := os.Stat(tmpPath); os.IsNotExist(statErr) {
		if err := os.WriteFile(tmpPath, dicomBytes, 0600); err != nil {
			writeJSON(w, http.StatusInternalServerError, map[string]string{
				"error": "écriture du fichier temporaire échouée : " + err.Error(),
			})
			return
		}
	}

	// ── 3. Borner les paramètres ────────────────────────────────────────────
	if req.Quality < 1 || req.Quality > 95 {
		req.Quality = 70
	}
	if req.MaxDim < 64 || req.MaxDim > 4096 {
		req.MaxDim = 640
	}

	// ── 4. Appel loader_cli.py ─────────────────────────────────────────────
	args := []string{
		"-m", "starhe_plugin.dicom.loader_cli",
		tmpPath,
		"--quality", strconv.Itoa(req.Quality),
		"--max-dim", strconv.Itoa(req.MaxDim),
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

	// ── 5. Injecter server_path dans la réponse ────────────────────────────
	var result map[string]any
	if err := json.Unmarshal(out, &result); err != nil {
		// Sortie non-JSON inattendue → forwarder telle quelle
		w.Header().Set("Content-Type", "application/json")
		w.Write(out) //nolint:errcheck
		return
	}
	result["server_path"] = tmpPath
	writeJSON(w, http.StatusOK, result)
}
