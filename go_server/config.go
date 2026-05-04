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

// serverDir renvoie le répertoire absolu de l'exécutable Go (go_server/).
// Utilisé pour calculer les chemins relatifs au projet indépendamment du CWD.
func serverDir() string {
	exe, err := os.Executable()
	if err != nil {
		return "."
	}
	return filepath.Dir(exe)
}

// defaultPythonExe renvoie le chemin absolu vers l'exécutable Python du venv,
// calculé depuis le dossier de l'exécutable (go_server/).
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
