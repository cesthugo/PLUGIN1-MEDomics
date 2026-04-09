# 👤 User Guide — STARHE Interface

> This document explains how to use the STARHE plugin interface prototype,  
> dedicated to hepatic ultrasound analysis for the detection of hepatocellular carcinoma (HCC).

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

## 📂 1. Loading One or More DICOM Files

1. In the sidebar, under **DICOM FILE**, click **📂 Load a DICOM file**.
2. The dialog allows selecting **one or more files** simultaneously (`Ctrl+click` or `Shift+click`).
3. Accepted formats:
   - Standard `.dcm` files
   - **Extensionless files** (e.g., `A0000`, `IM-0001`) — use the **"All files"** filter

**On import, automatically:**
- **Sensitive metadata** is removed from DICOM tags
- The **imager header banner** is **blacked out**
- **Pixel spacing** is extracted for millimeter measurements
- A **tab** is created for each loaded file, labeled with the DICOM date (`DD/MM/YYYY`)

---

## 📄 2. Multi-File Tabs

The **tab bar** is located at the bottom of the viewer, like a web browser.

| Action | Result |
|---|---|
| Click on a tab | Switches to that file (viewer, results, measurements, and playback state are preserved) |
| Click on a tab's **×** | Closes that file (the last tab resets everything) |
| Click on **+** (on the right) | Opens the file selector to add more DICOMs |
| Horizontal mouse wheel scroll | Scrolls if there are too many tabs |
| `Ctrl+Tab` | Next tab |
| `Ctrl+Shift+Tab` | Previous tab |
| `Ctrl+W` | Close active tab |

**Tab labels:** extracted from the `StudyDate` DICOM tag (format `DD/MM/YYYY`). If absent, the filename is used.

---

## ▶ 3. Navigating the Sequence

### Navigation Buttons
| Control | Action |
|---|---|
| **◄** | Previous frame |
| **►** | Next frame |
| Horizontal scrollbar | Drag to jump directly to a position |
| **► Play** | Start automatic playback |
| **⏸ Pause** | Pause playback |
| **⏮ Go to start** | Stop and return to frame 0 |

### Playback Speed
- **×-speed** slider (0.25× to 3.0×) in the sidebar
- Base speed is automatically calibrated from the DICOM `FrameTime` tag
- Below ×1: slowed playback; above: frames are skipped to accelerate

### Loop Mode
- Check **Loop** for playback to automatically restart at the end of the sequence

---

## ⌨️ 4. Keyboard Shortcuts

> Shortcuts are disabled when a text input field has focus.

### Video Navigation
| Key | Action |
|---|---|
| `Space` | ► Play / ⏸ Pause |
| `←` / `→` | Previous / Next frame |
| `Shift+←` / `Shift+→` | −10 / +10 frames |
| `Home` / `End` | First / Last frame |

### View Modes
| Key | Action |
|---|---|
| `P` | Toggle **Pan/Zoom** |
| `M` | Toggle **Measurement** |
| `S` | Toggle **Series scroll** (mouse wheel = frames) |
| `Esc` | Deselects active measurement, otherwise resets the view |
| `R` | **Reset** the view (zoom, pan, contrast, brightness) |

### Image Adjustments
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

**Activating pan:** Right-click → **Move / Zoom** or key `P` (cursor becomes a hand)

| Action | Result |
|---|---|
| **Click-drag** (Pan mode) | Moves the image in the canvas |
| **`−` / `+` buttons** (viewer header) | Zoom out / in (×1.25) |
| `Cmd+=` / `Ctrl+=` | Zoom in |
| `Cmd+-` / `Ctrl+-` | Zoom out |
| `Cmd+0` / `Ctrl+0` | Reset zoom to 100% |

The **zoom percentage** is displayed between the `−` and `+` buttons in the header.

To return to the initial view: key `R` or Right-click → **Reset view**

> **macOS note (Tk 9.0)**: trackpad scroll (mouse wheel) does not generate events in Tkinter with Tk 9.0.3. Use buttons or keyboard shortcuts to zoom.

---

## 📏 6. Measurement Tool (Multi-Segment)

**Activation:** Right-click → **Measurement tool** or key `M` (cursor becomes a crosshair)

### Drawing a New Segment
1. **Click and hold** on an empty area of the canvas
2. **Drag** to the endpoint — a yellow dashed line appears in real time
3. **Release** — the segment is fixed, the distance is displayed in yellow

Multiple measurements can be drawn simultaneously.

### Measurement Persistence
- Measurements **remain visible** when you change modes (Pan/Zoom, Normal, etc.)
- Measurements **follow zoom and pan**: they stay proportional to the image
- Only the **Reset view** action (key `R`) clears measurements

### Select / Edit / Delete
| Action | Result |
|---|---|
| Click **near a segment** | Selects it (turns orange) |
| Click-drag **on an endpoint** | Moves only that endpoint |
| Click-drag **on the middle of a segment** | Moves the entire segment |
| `Delete` or `BackSpace` | Deletes the selected segment |
| `Esc` | Deselects without deleting |

**Distance display:**
- If the DICOM contains calibration: **`X.X mm`**
- Otherwise: **`X.X px (no calibration)`**

> Calibration is extracted from `PixelSpacing`, `ImagerPixelSpacing`, or `SequenceOfUltrasoundRegions`.

---

## 📜 7. Series Scrolling (Frame-by-Frame Mouse Wheel)

**Activation:** Right-click → **Series scroll** or key `S`

| Action | Result |
|---|---|
| **Mouse wheel down** | Next frame |
| **Mouse wheel up** | Previous frame |

In **Normal** mode (no special mode activated), vertical left-button drag also scrolls frame by frame (1 frame per 8 pixels of movement).

---

## 🎨 8. Contrast & Brightness Adjustments

### Via Context Menu
- Right-click → **Contrast…** or **Brightness…** — opens a floating window with a slider
- **Reset** button to return to neutral values (contrast 1.0, brightness 0)

### Via Right-Click Hold
- **Hold right-click + drag**:
  - Right/left: contrast + / −
  - Down/up: brightness + / −
- The image updates in real time

### Via Shortcuts
- Key `C`: opens the Contrast window
- Key `L`: opens the Brightness window

---

## 🔄 9. Reset View

Key `R` or Right-click → **Reset view**: resets in one action:
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
   - `⟳ Processing…` — waiting
   - `✓ Done` — success
   - `✗ Error` — see the console
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

**Frames with tumor**: list of clickable 1-based frame numbers — clicking navigates to that frame.

**Automatic cache**: if the file has already been analyzed, results are restored **instantly** from MongoDB.

**🗑 Reset analysis**: clears the MongoDB results for this file to force a new analysis.

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

The **🌙 Dark theme** button at the bottom of the sidebar toggles between light and dark themes.  
The sidebar always stays dark in both modes.

---

## ⚠️ Important Notes

- **Anonymization**: each loaded file is anonymized **in memory**. The original file on disk **is not modified**.
- **Multiple open files**: each tab has its own independent state (playback, zoom, measurements, results). Switching tabs automatically saves and restores the full state.
- **Analysis in progress + tab switch**: if an AI analysis or preprocessing is in progress, do not switch tabs before completion to avoid state mixing.
- **mm calibration**: if `Pixel: N/A` is displayed, the measurement will be shown in pixels.
- **Extensionless files**: if your file does not appear in the file selector, change the filter to **"All files (*.*)"**.

---

*For technical questions, see [README.md](README.md) or [TODOLIST.md](TODOLIST.md).*

From the project root:

```powershell
# Windows (PowerShell)
.\run_tkinter.ps1

# macOS / Linux
./run_tkinter.sh
```

The window opens with the control sidebar on the left and the viewing area on the right.

---

## 📂 1. Loading a DICOM File

1. In the sidebar, under **DICOM FILE**, click **📂 Load a DICOM file**.
2. The dialog opens in the configured data folder.
3. Select your file:
   - Standard `.dcm` files
   - **Extensionless files** (e.g., `A0000`, `IM-0001` — Canon Aplio, Toshiba format, etc.)
   - Use the **"All files"** filter if your file does not appear

**On import, automatically:**
- **Sensitive metadata** (patient name, ID, dates, UIDs…) is removed from DICOM tags
- The **imager header banner** (patient information burned into pixels) is **blacked out**
- **Pixel spacing** is extracted to enable millimeter measurements

Non-sensitive information is displayed in the sidebar:
```
Modality : US
Size     : 1280×890
Frames   : 120
Pixel    : 0.275 mm/px
```
