/**
 * starheServer.js — Management of the standalone STARHE Go server inside MEDomics
 *
 * The STARHE Go server (port STARHE_PORT) is a process separate from the main
 * MEDomics Go server. It handles all /starhe/* routes (DICOM, analysis,
 * SSE) and is proxied by the MEDomics Go blueprint (see blueprints/starhe/).
 *
 * In development: the binary is looked up in PLUGIN1-MEDomics/go_server/.
 * In production : the binary must be packaged in resources/starhe/.
 *
 * Optional environment variable:
 *   STARHE_GO_SERVER_PATH  — absolute path to the binary (dev/prod override)
 */

import path from "path"
import { execFile } from "child_process"

const STARHE_PORT = 8082

let _starheProcess = null

/**
 * Starts the STARHE Go server in the background.
 * Resolves a Promise with the process, or rejects if the binary cannot be found.
 *
 * @param {boolean} isProd - true if the app is packaged (production)
 * @returns {Promise<ChildProcess>}
 */
export function startStarheServer(isProd) {
  return new Promise((resolve, reject) => {
    if (_starheProcess) {
      resolve(_starheProcess)
      return
    }

    const binaryName = process.platform === "win32" ? "go_server.exe" : "go_server"

    // Binary path
    let binaryPath
    if (process.env.STARHE_GO_SERVER_PATH) {
      // Explicit override (CI, tests, etc.)
      binaryPath = process.env.STARHE_GO_SERVER_PATH
    } else if (isProd) {
      binaryPath = path.join(process.resourcesPath, "starhe", binaryName)
    } else {
      // Development: PLUGIN1-MEDomics is a sibling directory of MEDomics
      binaryPath = path.join(process.cwd(), "..", "PLUGIN1-MEDomics", "go_server", binaryName)
    }

    // Python modules path
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
        if (err && err.killed) return // Normal shutdown
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
 * Cleanly stops the STARHE Go server.
 * To be called in the Electron app's `before-quit` handler.
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
