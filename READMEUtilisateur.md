# 👤 User Guide — STARHE Interface

> This document explains how to use the STARHE plug-in interface prototype,  
> dedicated to hepatic ultrasound analysis for hepatocellular carcinoma (HCC) detection.

---

## 🚀 Launching the Interface

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

## 📡 14. Live Analysis (Analyse en direct)

The **📡 Analyse en direct** button in the sidebar opens a dedicated window for real-time analysis of a live ultrasound feed.

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

## ⚠️ Important Notes

- **Anonymization**: each loaded file is anonymized **in memory**. The original file on disk **is not modified**.
- **Multiple open files**: each tab has its own independent state (playback, zoom, measurements, results). Switching tabs automatically saves and restores the entire state.
- **Analysis in progress + tab switch**: if an AI analysis or preprocessing is in progress, do not switch tabs before completion to avoid state mixing.
- **mm calibration**: if `Pixel: N/A` is displayed, the measurement will be shown in pixels.
- **Files without extension**: if your file does not appear in the selector, change the filter to **"All files (*.*)"**.

---

*For any technical questions, see the [README.md](README.md) or the [TODOLIST.md](TODOLIST.md).*

From the project root:

```powershell
# Windows (PowerShell)
.\run_tkinter.ps1

# macOS / Linux
./run_tkinter.sh
```

The window opens with the control sidebar on the left and the viewing area on the right.

---

## 📂 1. Load a DICOM File

1. In the sidebar, section **DICOM FILE**, click **📂 Load a DICOM file**.
2. The dialog opens in the configured data directory.
3. Select your file:
   - Standard `.dcm` files
   - **Files without extension** (e.g. `A0000`, `IM-0001` — Canon Aplio, Toshiba format, etc.)
   - Use the **"All files"** filter if your file does not appear

**On import, automatically:**
- **Sensitive metadata** (patient name, ID, dates, UIDs…) are removed from DICOM tags
- The imager **header banner** (patient information burned into pixels) is **blacked out**
- **Pixel spacing** is extracted to enable millimeter measurements

Non-sensitive information is displayed in the sidebar:
```
Modality : US
Size     : 1280×890
Frames   : 120
Pixel    : 0.275 mm/px
```

---

## ▶ 2. Sequence Navigation

### Navigation buttons
| Control | Action |
|---|---|
| **◀** | Previous frame |
| **▶** | Next frame |
| Horizontal scrollbar | Drag to go directly to a position |
| **▶ Play** | Start automatic playback |
| **⏸ Pause** | Pause playback |
| **⏮ Back to start** | Stop and return to frame 0 |

### Playback speed
- **×-speed** slider (0.25× to 3.0×, step 0.25×) in the sidebar — drag the cursor
- The **×1.00** label updates dynamically
- Base speed is automatically calibrated from the DICOM `FrameTime` tag
- Below ×1: slowed playback (extended interval); above: frames skipped to speed up

### Loop mode
- Check **Loop** to have playback automatically restart at the end of the sequence
- Uncheck for automatic stop at the last frame

---

## 🖱️ 3. Context Menu (Right-Click)

A **right-click on the canvas** opens a menu with 7 options.  
The active mode is marked with a **✓**.

```
╔══════════════════════════════╗
║ ✓ Move / Zoom                ║  ← current mode
║   Measure                    ║
║ ─────────────────────────────║
║   Contrast…                  ║
║   Brightness…                ║
║ ─────────────────────────────║
║   Series Scroll              ║
║ ─────────────────────────────║
║   Reset View                 ║
╚══════════════════════════════╝
```

---

## 🔍 4. Pan & Zoom

**Pan activation:** Right-click → **Move / Zoom** (cursor becomes a hand ✋)

| Action | Result |
|---|---|
| **Click-drag** (Pan mode) | Moves the image in the canvas |
| **`−` / `+` buttons** (viewer header) | Zoom out / in (×1.25) |
| `Cmd+=` / `Ctrl+=` | Zoom in |
| `Cmd+-` / `Ctrl+-` | Zoom out |
| `Cmd+0` / `Ctrl+0` | Reset zoom to 100% |

The **zoom percentage** is displayed between the buttons.

To return to the initial view: Right-click → **Reset View**

---

## 📏 5. Measurement Tool

**Activation:** Right-click → **Measure** (cursor becomes a crosshair ✛)

1. **Click and hold** the left button on the starting point of your measurement
2. **Drag** to the end point — a yellow dashed line appears in real time
3. **Release** to fix the measurement — the distance is displayed above the line

Multiple measurements can be drawn simultaneously. Measurements **persist** when you change modes and **follow zoom/pan** of the image.

**Distance display:**
- If the DICOM file contains spatial calibration: **`X.X mm`**
- Otherwise: **`X.X px (no calibration)`**

> The calibration is automatically extracted from the `PixelSpacing`,  
> `ImagerPixelSpacing`, or `SequenceOfUltrasoundRegions` tags (ultrasound).

To clear measurements: click **Reset View**.

---

## 📜 6. Series Scroll (Frame-by-Frame Wheel)

**Activation:** Right-click → **Series Scroll** (cursor becomes a double arrow ↕)

| Action | Result |
|---|---|
| **Wheel down** | Next frame |
| **Wheel up** | Previous frame |

Useful for browsing the sequence slowly without using the scrollbar.

---

## 🎨 7. Contrast & Brightness Settings

### Contrast
1. Right-click → **Contrast…**
2. A floating window opens with a slider (0.1 — 3.0, neutral = 1.0)
3. Move the slider — the image updates in real time
4. **Reset** button to return to the neutral value (1.0)

### Brightness
1. Right-click → **Brightness…**
2. Slider from −100 to +100 (neutral = 0)
3. Same behavior as contrast

Both windows can be open simultaneously.

---

## 🔄 8. Reset View

Right-click → **Reset View** — Resets in one action:
- Zoom → 1.0 (auto fit)
- Pan → centered
- Contrast → 1.0
- Brightness → 0
- Measurement → cleared

---

## ⚙️ 9. Preprocessing

Preprocessing uses **prepUS** to remove annotations and the imager's graphical interface.

1. First load a DICOM file
2. In the **PREPROCESSING** section, configure:
   - ☑ **Backscan (512×512)** — checked: displays the rectangular reconstruction (recommended for AI)
   - Uncheck to display the masked crop (original image without the imager interface)
3. Click **⚙ Preprocessing**
4. A status indicator appears below the button:
   - `⟳ Processing…` — pending
   - `✓ Done` — success
   - `✗ Error` — see console

5. Check **Show preprocessing result** to toggle between the original image and the result
6. The **Backscan (512×512)** checkbox can be toggled **after** processing without re-running prepUS

---

## 🧠 10. AI Analysis

1. Make sure you have loaded a DICOM file (and ideally run preprocessing)
2. Click **🧠 Launch STARHE Analysis**
3. Results are displayed in the **RESULTS** section:

| Field | Description |
|---|---|
| **HCC Risk** | Score 0–1 + label `Low` (green) or `High` (red) |
| **Lesions** | Number of detected lesions + average confidence score |

Detection bounding boxes are displayed directly on the canvas.

**Frames with tumor**: after analysis, the **Frames with tumor** section in the sidebar displays the list of frame numbers (1-based) where a lesion was detected, in **clickable blue**. Clicking a number navigates directly to that frame.

**Automatic cache**: if the `.dcm` file was analyzed in a previous session, results are restored **instantly** from MongoDB without re-running the AI models.

---

## 💬 11. Console

The **Console** at the bottom of the window displays in real time:
- Loading and anonymization steps
- Preprocessing progress
- AI analysis results
- Any errors

It is read-only. Error messages appear in red.

---

## 🌗 12. Light / Dark Theme

The **🌙 Dark theme** button at the bottom of the sidebar toggles between:
- **Light theme** — main area `#f4f6fb`, white cards
- **Dark theme** — main area `#1a1a2e`, cards `#16213e`

The sidebar always remains dark in both modes.

---

## 📡 13. Live Analysis (Analyse en direct)

The **📡 Analyse en direct** button in the sidebar opens a dedicated window for real-time analysis of a live ultrasound feed.

### Opening the window

Click **📡 Analyse en direct** in the main sidebar. A new window appears.  
Re-clicking while the window is already open brings it to the foreground.

### Choosing an input source

| Source | Description |
|---|---|
| **C-STORE DICOM** | Receives DICOM images sent directly by the ultrasound machine over the network. Enter the AE title and TCP port, then click **Start**. |
| **Folder** | Watches a local directory for new `.dcm` files and pushes them into the pipeline every 0.5 s. |
| **HDMI Capture Card** | Captures live video from a USB HDMI capture card plugged into the ultrasound machine's HDMI output. |

### HDMI source — required hardware

> ⚠ **A USB HDMI capture card is required** (Elgato HD60 S+, AVerMedia, Magewell USB Capture, etc.).  
> Plugging HDMI directly into a Mac Thunderbolt/USB-C port will **not** work — those ports are output-only.

Click **🔍 Scan** to detect connected devices:
- `✅ Capture card detected` — click **▶ Démarrer** to start.
- `⚠ Matériel requis` (orange) — no capture card found. Check the USB connection and retry.

### Live display

- Video preview at ~30 fps with bounding boxes overlaid over detected lesions.
- HCC Risk score (`Low` / `High`) updated every 16 frames.
- ROI auto-detected after the first 30 frames (no manual action needed).

---

## ⚠️ Important Notes

- **Anonymization**: each loaded file is automatically anonymized in memory. The original file on disk **is not modified**.
- **Imager banner**: the header banner (visible patient information) is automatically blacked out. If the banner is not detected, check that the image has a black background around the ultrasound cone.
- **mm calibration**: if `Pixel: N/A` is displayed in the sidebar, the DICOM file does not contain spatial calibration and the measurement will be shown in pixels.
- **Files without extension**: if your file does not appear in the selector, change the filter to **"All files (*.*)"**.

---

*For any technical questions, see the [README.md](README.md) or the [TODOLIST.md](TODOLIST.md).*
