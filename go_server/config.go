// config.go — STARHE server configuration
//
// All values can be overridden via environment variables.
// Example:
//
//	$env:PORT = "9090"
//	$env:STARHE_PYTHON_EXE = "C:\Python313\python.exe"
package main

import (
	"context"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
)

type appConfig struct {
	// Network
	Port string

	// Python — "venv" mode (dev)
	PythonExe     string // Absolute path to the venv's python
	PythonModPath string // Root directory of Python modules (contains starhe_plugin/)

	// Python — "bundle" mode (packaged Electron). If non-empty, the
	// PyInstaller starhe_worker executable is used instead of the venv.
	// Convention: starhe_worker --module <name> <args...>
	WorkerBin string

	// UI — React build directory served under /ui/
	UIDir string

	// AI weights directory (.pth). Must mirror exactly the resolution
	// in config.py: STARHE_WEIGHTS_DIR, else the plugin's models/.
	WeightsDir string

	// MongoDB
	MongoURI        string
	MongoDatabase   string
	MongoCollection string
}

// serverDir returns the absolute directory of the Go executable (go_server/).
// Used to compute project-relative paths independently of the CWD.
func serverDir() string {
	exe, err := os.Executable()
	if err != nil {
		return "."
	}
	return filepath.Dir(exe)
}

// defaultPythonExe returns the absolute path to the venv's Python executable,
// computed from the executable's directory (go_server/).
func defaultPythonExe() string {
	base := filepath.Join(serverDir(), "..", "pythonCode", "modules", "starhe_plugin", ".venv")
	if runtime.GOOS == "windows" {
		return filepath.Join(base, "Scripts", "python.exe")
	}
	return filepath.Join(base, "bin", "python")
}

var cfg = appConfig{
	Port: envOr("PORT", "8082"),

	PythonExe:     envOr("STARHE_PYTHON_EXE", defaultPythonExe()),
	PythonModPath: envOr("STARHE_PYTHON_PATH", filepath.Join(serverDir(), "..", "pythonCode", "modules")),
	WorkerBin:     os.Getenv("STARHE_WORKER_BIN"), // empty in dev, set by Electron in prod

	UIDir: envOr("STARHE_UI_DIR", filepath.Join(serverDir(), "..", "renderer", "dist")),

	WeightsDir: envOr("STARHE_WEIGHTS_DIR",
		filepath.Join(serverDir(), "..", "pythonCode", "modules", "starhe_plugin", "models")),

	MongoURI:        envOr("MONGO_URI", "mongodb://localhost:54017/"),
	MongoDatabase:   envOr("MONGO_DB", "medomics"),
	MongoCollection: envOr("MONGO_COLL", "starhe_results"),
}

func envOr(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}

// pythonCmd builds the command to run a STARHE Python module.
// In bundle mode (WorkerBin set): starhe_worker --module <name> <args...>
// In venv mode:                   python -m starhe_plugin.<name> <args...>
// Env and Dir are pre-configured (PYTHONPATH, PYTHONUTF8, cwd).
func pythonCmd(ctx context.Context, module string, args ...string) *exec.Cmd {
	var cmd *exec.Cmd
	if cfg.WorkerBin != "" {
		// Bundle mode: the PyInstaller worker is self-contained (resolves its own
		// paths via sys._MEIPASS). Do NOT set a working directory at all — the
		// source tree (pythonCode/modules) is absent from the bundle, and on
		// Windows chdir'ing into the worker's own dir intermittently fails with
		// "The system cannot find the file specified". Inheriting the parent cwd
		// works on every platform.
		full := append([]string{"--module", module}, args...)
		cmd = exec.CommandContext(ctx, cfg.WorkerBin, full...)
		cmd.Env = append(os.Environ(), "PYTHONUTF8=1")
	} else {
		// Dev/venv mode: run the module from the source tree.
		full := append([]string{"-m", "starhe_plugin." + module}, args...)
		cmd = exec.CommandContext(ctx, cfg.PythonExe, full...)
		cmd.Dir = cfg.PythonModPath
		cmd.Env = append(os.Environ(),
			"PYTHONPATH="+cfg.PythonModPath,
			"PYTHONUTF8=1", // force UTF-8 on Windows
		)
	}
	return cmd
}

