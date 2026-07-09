// handlers_dicom.go — Additional endpoints for the DICOM service (frame loading)
//
// POST /starhe/dicom/load   → loads a DICOM via Python and returns all frames as base64 JPEG
//   Accepts two formats:
//     - multipart/form-data  : "file" field (browser upload), "quality" and "max_dim" parameters
//     - application/json     : {"dicom_path":"...","quality":70,"max_dim":640} (Electron / CLI)
// DELETE /starhe/cache      → deletes a file's MongoDB cache by path (?path=...)
package main

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/bson"
)

// ── POST /starhe/dicom/load ────────────────────────────────────────────────
//
// Accepts two formats:
//
//  1. multipart/form-data (browser upload):
//     "file" field     → DICOM file bytes
//     "quality" field  → optional int (default 70)
//     "max_dim" field  → optional int (default 640)
//
//  2. application/json (Electron / path input):
//     { "dicom_path": "/absolute/path/file.dcm", "quality": 70, "max_dim": 640 }
//
// Response: JSON returned directly by loader_cli.py.
func dicomLoadHandler(w http.ResponseWriter, r *http.Request) {
	quality := 70
	maxDim  := 640
	var dicomPath string
	var tmpToDelete string  // temporary file to delete after processing
	var originalName string  // original name provided by the browser (upload mode)

	ct := r.Header.Get("Content-Type")

	if strings.Contains(ct, "multipart/form-data") {
		// ── Browser upload mode ─────────────────────────────────────────────
		// 500 MB in-memory limit (multi-frame DICOMs can be heavy)
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

		// Read the content into memory to compute the SHA-256 hash
		fileBytes, err := io.ReadAll(f)
		if err != nil {
			writeJSON(w, http.StatusInternalServerError, map[string]string{
				"error": "erreur lecture fichier uploadé : " + err.Error(),
			})
			return
		}

		// Deterministic content-based name: same file → same path → cache hit
		hash := sha256.Sum256(fileBytes)
		hashStr := hex.EncodeToString(hash[:])[:24]
		tmpPath := filepath.Join(os.TempDir(), "starhe_upload_"+hashStr+".dcm")
		tmpToDelete = tmpPath

		// Only write if the file does not exist yet (same content already present)
		if _, statErr := os.Stat(tmpPath); os.IsNotExist(statErr) {
			if err := os.WriteFile(tmpPath, fileBytes, 0600); err != nil {
				writeJSON(w, http.StatusInternalServerError, map[string]string{
					"error": "erreur écriture fichier temporaire : " + err.Error(),
				})
				return
			}
		}

		dicomPath = tmpPath
		originalName = header.Filename

		// Optional parameters from the form
		if v := r.FormValue("quality"); v != "" {
			if n, err := strconv.Atoi(v); err == nil {
				quality = n
			}
		}
		if v := r.FormValue("max_dim"); v != "" {
			if n, err := strconv.Atoi(v); err == nil {
				maxDim = n
			}
		}

	} else {
		// ── JSON mode (Electron / path input) ───────────────────────────────
		var req struct {
			DicomPath string `json:"dicom_path"`
			Quality   int    `json:"quality"`
			MaxDim    int    `json:"max_dim"`
		}
		req.Quality = quality
		req.MaxDim  = maxDim

		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			writeJSON(w, http.StatusBadRequest, map[string]string{
				"error": "corps de requête JSON invalide : " + err.Error(),
			})
			return
		}
		if req.DicomPath == "" {
			writeJSON(w, http.StatusBadRequest, map[string]string{
				"error": "dicom_path est requis",
			})
			return
		}
		if _, err := os.Stat(req.DicomPath); err != nil {
			writeJSON(w, http.StatusBadRequest, map[string]string{
				"error": "fichier dicom_path introuvable : " + req.DicomPath,
			})
			return
		}
		dicomPath = req.DicomPath
		if req.Quality > 0 { quality = req.Quality }
		if req.MaxDim  > 0 { maxDim  = req.MaxDim  }
	}

	// In upload mode: keep the temp file — it will be used by /starhe/analyze.
	// It is deleted via DELETE /starhe/cache?path=<server_path>.
	// (no defer os.Remove here)

	// Clamp the parameters
	if quality < 1 || quality > 95 { quality = 70  }
	if maxDim  < 64 || maxDim > 4096 { maxDim = 640 }

	// Timeout: 300 s for large multi-frame DICOM files (J2K Lossless is slow to decode)
	ctx, cancel := context.WithTimeout(r.Context(), 300*time.Second)
	defer cancel()

	args := []string{
		dicomPath,
		"--quality", strconv.Itoa(quality),
		"--max-dim", strconv.Itoa(maxDim),
	}

	cmd := pythonCmd(ctx, "dicom.loader_cli", args...)

	var stderr bytes.Buffer
	cmd.Stderr = &stderr

	out, err := cmd.Output()
	if err != nil {
		// On error, clean up the temp file if applicable
		if tmpToDelete != "" {
			os.Remove(tmpToDelete)
		}
		// loader_cli.py writes the JSON error + traceback to stdout before sys.exit(1).
		// Include it in the response so the client can display the actual error.
		errResp := map[string]string{
			"error":  "subprocess Python échoué : " + err.Error(),
			"stderr": stderr.String(),
		}
		if len(out) > 0 {
			errResp["stdout"] = string(out)
			// If the Python JSON contains an "error" field, expose it directly.
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

	// If the file came from a multipart upload, inject server_path into the JSON
	// so the React client knows which path to send to /starhe/analyze.
	if tmpToDelete != "" {
		var obj map[string]interface{}
		if err := json.Unmarshal(out, &obj); err == nil {
			obj["server_path"] = tmpToDelete
			if originalName != "" {
				obj["file_name"] = originalName
			}
			if patched, err := json.Marshal(obj); err == nil {
				out = patched
			}
		}
	}

	// Forward the JSON to the client
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(http.StatusOK)
	w.Write(out) //nolint:errcheck
}

// ── DELETE /starhe/cache ───────────────────────────────────────────────────
//
// URL parameter: ?path=<absolute_dicom_path>
//
// Deletes the MongoDB documents whose "file_path" field matches the given path.
func deleteCacheHandler(w http.ResponseWriter, r *http.Request) {
	path := r.URL.Query().Get("path")
	if path == "" {
		writeJSON(w, http.StatusBadRequest, map[string]string{
			"error": "paramètre 'path' requis",
		})
		return
	}

	ctx, cancel := context.WithTimeout(r.Context(), 5*time.Second)
	defer cancel()

	result, err := collection().DeleteMany(ctx, bson.D{{Key: "file_path", Value: path}})
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{
			"error": err.Error(),
		})
		return
	}

	writeJSON(w, http.StatusOK, map[string]any{
		"deleted": result.DeletedCount,
		"path":    path,
	})
}
