/**
 * starheServer.js — Gestion du serveur Go STARHE standalone dans MEDomics
 *
 * Le serveur Go STARHE (port STARHE_PORT) est un processus séparé du serveur
 * Go MEDomics principal. Il gère toutes les routes /starhe/* (DICOM, analyse,
 * SSE) et est proxifié par le blueprint Go MEDomics (voir blueprints/starhe/).
 *
 * En développement : le binaire est cherché dans PLUGIN1-MEDomics/go_server/.
 * En production    : le binaire doit être packagé dans resources/starhe/.
 *
 * Variable d'environnement optionnelle :
 *   STARHE_GO_SERVER_PATH  — chemin absolu vers le binaire (override dev/prod)
 */

import path from "path"
import { execFile } from "child_process"

const STARHE_PORT = 8082

let _starheProcess = null

/**
 * Démarre le serveur Go STARHE en arrière-plan.
 * Résout une Promise avec le process, ou rejette si le binaire est introuvable.
 *
 * @param {boolean} isProd - true si l'app est packagée (production)
 * @returns {Promise<ChildProcess>}
 */
export function startStarheServer(isProd) {
  return new Promise((resolve, reject) => {
    if (_starheProcess) {
      resolve(_starheProcess)
      return
    }

    const binaryName = process.platform === "win32" ? "go_server.exe" : "go_server"

    // Chemin du binaire
    let binaryPath
    if (process.env.STARHE_GO_SERVER_PATH) {
      // Override explicite (CI, tests, etc.)
      binaryPath = process.env.STARHE_GO_SERVER_PATH
    } else if (isProd) {
      binaryPath = path.join(process.resourcesPath, "starhe", binaryName)
    } else {
      // Développement : PLUGIN1-MEDomics est un dossier frère de MEDomics
      binaryPath = path.join(process.cwd(), "..", "PLUGIN1-MEDomics", "go_server", binaryName)
    }

    // Chemin des modules Python
    const pythonModPath = isProd
      ? path.join(process.resourcesPath, "starhe", "pythonCode", "modules")
      : path.join(process.cwd(), "..", "PLUGIN1-MEDomics", "pythonCode", "modules")

    const env = {
      ...process.env,
      PORT: String(STARHE_PORT),
      PYTHON_MOD_PATH: pythonModPath,
    }

    console.log(`[STARHE] Démarrage du serveur sur port ${STARHE_PORT}`)
    console.log(`[STARHE] Binaire : ${binaryPath}`)

    _starheProcess = execFile(
      binaryPath,
      [STARHE_PORT, isProd ? "prod" : "dev", process.cwd(), require("os").tmpdir()],
      { env, windowsHide: true },
      (err) => {
        if (err && err.killed) return // Arrêt normal
        if (err) console.error("[STARHE] Erreur process :", err.message)
        _starheProcess = null
      }
    )

    _starheProcess.stdout?.on("data", (d) => console.log("[STARHE Go]", d.toString().trim()))
    _starheProcess.stderr?.on("data", (d) => console.error("[STARHE Go ERR]", d.toString().trim()))

    _starheProcess.on("spawn", () => {
      console.log(`[STARHE] Serveur démarré (PID ${_starheProcess.pid})`)
      resolve(_starheProcess)
    })

    _starheProcess.on("error", (err) => {
      console.error("[STARHE] Impossible de démarrer le serveur :", err.message)
      _starheProcess = null
      reject(err)
    })
  })
}

/**
 * Arrête proprement le serveur Go STARHE.
 * À appeler dans le handler `before-quit` de l'app Electron.
 */
export function stopStarheServer() {
  if (_starheProcess) {
    try {
      _starheProcess.kill()
      console.log("[STARHE] Serveur arrêté")
    } catch {
      console.log("[STARHE] Serveur déjà arrêté")
    }
    _starheProcess = null
  }
}
