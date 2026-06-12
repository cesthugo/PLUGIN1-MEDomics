# 👤 User Guide — STARHE Interface

> This document explains how to use the STARHE plug-in interface,  
> dedicated to hepatic ultrasound analysis for hepatocellular carcinoma (HCC) detection.
>
> **Version 0.6.3** — Last updated: 12 juin 2026

---

## 📥 Installation (Standalone App)

The packaged application is available on the [GitHub Releases page](https://github.com/cesthugo/PLUGIN1-MEDomics/releases).

| Platform | File to download | Notes |
|---|---|---|
| macOS Apple Silicon (M1/M2/M3) | `STARHE-0.6.3-mac-arm64.dmg` | Drag STARHE to Applications |
| macOS Intel | `STARHE-0.6.3-mac-x64.dmg` | Drag STARHE to Applications |
| Linux (Debian/Ubuntu) | `STARHE-0.6.3-linux-amd64.deb` | `sudo dpkg -i STARHE-*.deb` |
| Windows | `STARHE-0.6.3-win-x64.exe` | Run the NSIS installer |

> **macOS — first launch**: the app is not signed. Right-click → **Open** → **Open Anyway** to bypass Gatekeeper.  
> **Windows — first launch**: click **More info** → **Run anyway** to bypass SmartScreen.  
> **MongoDB required**: STARHE needs a MongoDB instance running on port `54017`. This is the only external dependency — it is not bundled in the app.

On first launch, a window will automatically download the AI model weights (~750 MB). An internet connection is required for this step only.

---

## 🚀 Launching the Interface (Development Mode)

```powershell
# Windows (PowerShell)
.\run_tkinter.ps1

# macOS / Linux
./run_tkinter.sh
```

The window opens with the control sidebar on the left and the viewing area on the right.

---

## 📂 1. Load One or More DICOM Files

1. In the sidebar, section **DICOM FILE**, click **📂 Load a DICOM file**.
2. The dialog allows selecting **one or more files** simultaneously (`Ctrl+click` or `Shift+click`).
3. Accepted formats:
   - Standard `.dcm` files
   - **Files without extension** (e.g. `A0000`, `IM-0001`) — use the **"All files"** filter

**On import, automatically:**
- **Sensitive metadata** are removed from DICOM tags
- The imager **header banner** is **blacked out**
- **Pixel spacing** is extracted for millimeter measurements
- A **tab** is created for each loaded file, labeled with the DICOM date (`DD/MM/YYYY`)

---

## 📄 2. Multi-File Tabs

The **tab bar** is located at the bottom of the viewer, like a web browser.

| Action | Result |
|---|---|
| Click on a tab | Switches to that file (viewer, results, measurements and playback state are preserved) |
| Click on a tab's **×** | Closes that file (the last tab resets everything) |
| Click on **+** (on the right) | Opens the file selector to add more DICOM files |
| Horizontal mouse wheel scroll | Scrolls if too many tabs |
| `Ctrl+Tab` | Next tab |
| `Ctrl+Shift+Tab` | Previous tab |
| `Ctrl+W` | Close active tab |

**Tab labels:** extracted from the DICOM `StudyDate` tag (format `DD/MM/YYYY`). If absent, the file name is used.

---

## ▶ 3. Sequence Navigation

### Navigation buttons
| Control | Action |
|---|---|
| **◄** | Previous frame |
| **►** | Next frame |
| Horizontal scrollbar | Drag to go directly to a position |
| **► Play** | Start automatic playback |
| **⏸ Pause** | Pause playback |
| **⏮ Back to start** | Stop and return to frame 0 |

### Playback speed
- **×-speed** slider (0.25× to 3.0×) in the sidebar
- Base speed is automatically calibrated from the DICOM `FrameTime` tag
- Below ×1: slowed playback; above: frames skipped to speed up

### Loop mode
- Check **Loop** to have playback automatically restart at the end of the sequence

---

## ⌨️ 4. Keyboard Shortcuts

> Shortcuts are disabled when an input field has focus.

### Video navigation
| Key | Action |
|---|---|
| `Space` | ► Play / ⏸ Pause |
| `←` / `→` | Previous / Next frame |
| `Shift+←` / `Shift+→` | −10 / +10 frames |
| `Home` / `End` | First / Last frame |

### View modes
| Key | Action |
|---|---|
| `P` | Toggle **Pan/Zoom** |
| `M` | Toggle **Measure** |
| `S` | Toggle **Series Scroll** (wheel = frames) |
| `Esc` | Deselect active measurement, otherwise reset view |
| `R` | **Reset** view (zoom, pan, contrast, brightness) |

### Image adjustments
| Key | Action |
|---|---|
| `C` | Open **Contrast** dialog |
| `L` | Open **Brightness** dialog |
| `+` or `=` | Playback speed ×1.25 |
| `-` | Playback speed ×0.80 |
| `B` | Toggle **Loop** |

> **Note:** `Cmd+=` / `Ctrl+=` and `Cmd+-` / `Ctrl+-` only control zoom (see below), not playback speed.

### Zoom
| Key | Action |
|---|---|
| `Cmd+=` / `Ctrl+=` | **Zoom in** (×1.25) |
| `Cmd+-` / `Ctrl+-` | **Zoom out** (÷1.25) |
| `Cmd+0` / `Ctrl+0` | **Reset** zoom to 100% |

### Tabs
| Key | Action |
|---|---|
| `Ctrl+Tab` | Next tab |
| `Ctrl+Shift+Tab` | Previous tab |
| `Ctrl+W` | Close active tab |

---

## 🔍 5. Pan & Zoom

**Pan activation:** Right-click → **Move / Zoom** or key `P` (cursor becomes a hand)

| Action | Result |
|---|---|
| **Click-drag** (Pan mode) | Moves the image in the canvas |
| **`−` / `+` buttons** (viewer header) | Zoom out / in (×1.25) |
| `Cmd+=` / `Ctrl+=` | Zoom in |
| `Cmd+-` / `Ctrl+-` | Zoom out |
| `Cmd+0` / `Ctrl+0` | Reset zoom to 100% |

The **zoom percentage** is displayed between the `−` and `+` buttons in the header.

To return to the initial view: key `R` or Right-click → **Reset View**

> **macOS note (Tk 9.0)**: trackpad scroll (wheel) does not generate events in Tkinter with Tk 9.0.3. Use buttons or keyboard shortcuts to zoom.

---

## 📏 6. Measurement Tool (Multi-Segments)

**Activation:** Right-click → **Measurement tool** or key `M` (cursor becomes a crosshair)

### Draw a new segment
1. **Click and hold** on an empty area of the canvas
2. **Drag** to the end point — a yellow dashed line appears in real time
3. **Release** — the segment is fixed, the distance is displayed in yellow

Multiple measurements can be drawn simultaneously.

### Measurement persistence
- Measurements **remain visible** when you change modes (Pan/Zoom, Normal, etc.)
- Measurements **follow zoom and pan**: they remain proportional to the image
- Only the **Reset View** action (key `R`) clears the measurements

### Select / Edit / Delete
| Action | Result |
|---|---|
| Click **near a segment** | Selects it (turns orange) |
| Click-drag **on an endpoint** (extremity) | Moves only that endpoint |
| Click-drag **on the middle of a segment** | Moves the entire segment |
| `Delete` or `BackSpace` | Deletes the selected segment |
| `Esc` | Deselects without deleting |

**Distance display:**
- If the DICOM contains a calibration: **`X.X mm`**
- Otherwise: **`X.X px (no calibration)`**

> The calibration is extracted from `PixelSpacing`, `ImagerPixelSpacing`, or `SequenceOfUltrasoundRegions`.

---

## 📜 7. Series Scroll (Frame-by-Frame Wheel)

**Activation:** Right-click → **Series Scroll** or key `S`

| Action | Result |
|---|---|
| **Wheel down** | Next frame |
| **Wheel up** | Previous frame |

In **Normal** mode (no special mode activated), vertical left-button drag also scrolls frame by frame (1 frame every 8 pixels of movement).

---

## 🎨 8. Contrast & Brightness Settings

### Via the context menu
- Right-click → **Contrast…** or **Brightness…** — opens a floating window with slider
- **Reset** button to return to neutral values (contrast 1.0, brightness 0)

### Via held right-click
- **Hold right-click + drag**:
  - Right/left: contrast + / −
  - Down/up: brightness + / −
- The image updates in real time

### Via shortcuts
- Key `C`: opens the Contrast window
- Key `L`: opens the Brightness window

---

## 🔄 9. Reset View

Key `R` or Right-click → **Reset View**: resets in one action:
- Zoom → 1.0 (auto fit)
- Pan → centered
- Contrast → 1.0
- Brightness → 0
- Mode → Normal
- Measurements → cleared

---

## ⚙️ 10. Preprocessing

1. First load a DICOM file
2. In the **PREPROCESSING** section, configure:
   - ☑ **Backscan (512×512)** — checked: displays the rectangular reconstruction (recommended for AI)
3. Click **⚙ Preprocessing**
4. Status indicator:
   - `⟳ Processing…` — pending
   - `✓ Done` — success
   - `✗ Error` — see console
5. Check **Show preprocessing result** to toggle between the original image and the result

---

## 🧠 11. AI Analysis

1. Load a DICOM and run preprocessing (optional)
2. Click **🧠 Launch STARHE Analysis**
3. **RESULTS** section:

| Field | Description |
|---|---|
| **Mode** | Analyzed surface (Backscan 512×512 / Preprocessing / Original) |
| **HCC Risk** | Score 0–1 + label `Low` (green) or `High` (red) |
| **Lesions** | Number of frames with lesion(s) |

**Frames with tumor**: list of 1-based clickable numbers — clicking navigates to that frame.

**Automatic cache**: if the file was already analyzed, results are restored **instantly** from MongoDB.

**🗑 Reset analysis**: deletes the MongoDB results for this file to force a new analysis.

---

## 💬 12. Console

The **Console** at the bottom of the window displays in real time:
- Loading and anonymization steps
- Preprocessing progress
- AI analysis results
- Any errors (in red)

It is read-only.

---

## 🎗 13. Light / Dark Theme

The **🌙 Dark theme** button at the bottom of the sidebar toggles between light and dark theme.  
The sidebar always remains dark in both modes.

---

## 📋 14. Batch Analysis (Analyse en lot)

The **📋 Analyse en lot (batch)** button in the sidebar opens the batch modal to analyze multiple DICOM files sequentially and manage results.

### Opening the modal

Click **📋 Analyse en lot (batch)** in the sidebar. A full-screen modal opens.

### Loading files

| Method | Description |
|---|---|
| **Drag-and-drop** | Drag `.dcm`, `.dicom`, or extension-less files directly onto the drop zone |
| **Click the drop zone** | Opens a file picker to select one or more DICOM files |
| **Folder button** | Loads an entire directory — only DICOM files are kept |
| **Absolute path** | Type a server-side path and click **Ajouter** |
| **⬆ Importer JSON** | Reload a previously exported JSON file (see below) — files appear instantly with their results pre-filled, no re-analysis needed |

### Running the batch

1. Add the files you want to analyze.
2. Select the analysis mode (RISK + DETECT / RISK / DETECT) in the header.
3. Click **▶ Lancer le batch**.
4. Each file is analyzed sequentially; progress is shown inline per file.

### Results table (Récapitulatif)

Once at least one file is done, a summary table appears at the bottom:

| Column | Description |
|---|---|
| Checkbox | Select individual files to open |
| Fichier | File name |
| Risque CHC | Risk label (Risque faible / Risque élevé) |
| Score | Numeric risk score (%) |
| Lésions | Number of detected lesions |
| Ouvrir | **→ Tab** button — opens that file in the viewer with detections already overlaid |

**Opening multiple files at once:**
- Check the files you want, then click **↗ Ouvrir sélection (N)**.
- Or click **↗ Tout ouvrir (N)** to open all analyzed files at once.
- Each file opens in its own tab with the risk score and bounding boxes pre-injected — no re-analysis required.

> If the session was restarted and the server temp file has expired, a file picker opens automatically so you can re-upload the original DICOM. The results (bboxes + risk) from the JSON are already loaded — only the image data needs to be re-provided.

### Exporting results

| Button | Format | Contents |
|---|---|---|
| **⬇ Générer JSON** | `.json` | Full results including all bounding boxes per frame (`detections_per_frame`) — reloadable in a future session |
| **⬇ Générer CSV** | `.csv` | Summary table (file name, risk label, score, lesion count) |

### Importing a previous JSON

Click **⬆ Importer JSON**, select a `starhe_batch_*.json` file generated previously.  
The files appear in the list with status ✅ and their results already filled in.  
Click **→ Tab** or **↗ Tout ouvrir** to open them in the viewer without re-running the AI.


---

## 📡 15. Live Analysis (Analyse en direct)

The **📡 Analyse en direct** button in the sidebar opens a dedicated window for real-time analysis of a live ultrasound feed.

> **Architecture** : clicking **▶ Démarrer** tells the Go server to launch `run_live.py` as a subprocess. The Python process handles the selected input source and streams results back to the UI over SSE. The video preview is sent immediately (before inference), so the image is always fluid even if the AI is slower.

### Opening the window

Click **📡 Analyse en direct** in the main sidebar. A new window appears.  
Re-clicking while the window is already open brings it to the foreground.

### Choosing an input source

Select the source using the radio buttons at the top of the window:

| Source | Description |
|---|---|
| **C-STORE DICOM** | Receives DICOM images sent directly by the ultrasound machine over the network (C-STORE SCP protocol). Enter the AE title and TCP port, then click **Start**. |
| **Folder** | Watches a local directory for new `.dcm` files. New files are read and pushed into the inference pipeline automatically every 0.5 s. |
| **HDMI Capture Card** | Captures live video from a USB HDMI capture card connected to the ultrasound machine's video output. |

### HDMI source — required hardware

A **USB HDMI capture card** is required (e.g. Elgato HD60 S+, AVerMedia Live Gamer, Magewell USB Capture).

> ⚠ **Plugging an HDMI cable directly into a Mac Thunderbolt/USB-C port will not work** — those ports are video *output* only. A capture card converts the HDMI signal to USB video input.

After selecting **HDMI**, click **🔍 Scan** to detect connected devices. The status label updates:
- `✅ Capture card detected` — a recognized device was found, the **Start** button is enabled.
- `⚠ Matériel requis` (orange) — no recognized capture card found. Check the USB connection and retry.
- `🔴 Aucun périphérique` — no video devices found at all.

Select a resolution in the dropdown (`Auto`, `1080p`, `720p`, `PAL`, `SD`). **Auto** lets the capture card choose its default.

### Starting and stopping

Click **▶ Démarrer** to start live acquisition and inference.  
Click **⏹ Arrêter** to stop.

### Live display

- The central canvas shows the live video feed at ~30 fps, independent of the inference rate.
- **Bounding boxes** (red) are drawn over each detected lesion in real time.
- The **HCC Risk Score** and label (`Low risk` / `High risk`) update every 16 frames from the C3D model.
- A **FPS counter** in the header shows the current capture frame rate.

### ROI calibration

The pipeline automatically detects the ultrasound cone after the first 30 frames and crops the image to the region of interest before sending it to the AI models. No manual action is needed.

---

## ⚠️ 16. Important Notes

- **Anonymization**: each loaded file is anonymized **in memory**. The original file on disk **is not modified**.
- **Multiple open files**: each tab has its own independent state (playback, zoom, measurements, results). Switching tabs automatically saves and restores the entire state.
- **Analysis in progress + tab switch**: if an AI analysis or preprocessing is in progress, do not switch tabs before completion to avoid state mixing.
- **mm calibration**: if `Pixel: N/A` is displayed, the measurement will be shown in pixels.
- **Files without extension**: if your file does not appear in the selector, change the filter to **"All files (*.*)"**.

---

*For any technical questions, see the [README.md](README.md) or the [TODOLIST.md](TODOLIST.md).*
