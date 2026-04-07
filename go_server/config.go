// config.go — Configuration du serveur STARHE
//
// Toutes les valeurs peuvent être surchargées via variables d'environnement.
// Exemple :
//
//	$env:PORT = "9090"
//	$env:STARHE_PYTHON_EXE = "C:\Python313\python.exe"
package main

import (
	"os"
	"path/filepath"
	"runtime"
)

type appConfig struct {
	// Réseau
	Port string

	// Python
	PythonExe     string // Chemin absolu vers python du venv
	PythonModPath string // Dossier racine des modules Python (contient starhe_plugin/)

	// MongoDB
	MongoURI        string
	MongoDatabase   string
	MongoCollection string
}

// defaultPythonExe renvoie le chemin par défaut de l'exécutable Python du venv,
// relatif au dossier go_server/ (../pythonCode/modules/starhe_plugin/.venv/…).
func defaultPythonExe() string {
	base := filepath.Join("..", "pythonCode", "modules", "starhe_plugin", ".venv")
	if runtime.GOOS == "windows" {
		return filepath.Join(base, "Scripts", "python.exe")
	}
	return filepath.Join(base, "bin", "python")
}

var cfg = appConfig{
	Port: envOr("PORT", "8080"),

	PythonExe:     envOr("STARHE_PYTHON_EXE", defaultPythonExe()),
	PythonModPath: envOr("STARHE_PYTHON_PATH", filepath.Join("..", "pythonCode", "modules")),

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
