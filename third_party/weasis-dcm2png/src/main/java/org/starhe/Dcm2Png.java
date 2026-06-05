/*
 * STARHE Plugin — Weasis DICOM-to-PNG CLI
 *
 * Thin wrapper around weasis-dicom-tools Transcoder.dcm2image.
 * Exports each frame of a multi-frame DICOM as a PNG applying Modality LUT
 * and VOI LUT (Window/Level) exactly as Weasis would display it.
 *
 * Usage:
 *   java -Djava.library.path=<native_dir> \
 *        --enable-native-access=ALL-UNNAMED  \
 *        -jar weasis-dcm2png.jar <input.dcm> <output_dir>
 *
 * Stdout (one line each, machine-readable for the Python wrapper):
 *   fps=<float>          — frames per second from DICOM FrameTime / CineRate
 *   frames=<int>         — total number of exported frames
 *   frame=<abs_path>     — one line per output PNG (sorted, 1-indexed)
 *
 * Exit codes: 0 = success, 1 = bad args / file not found, 2 = OpenCV load
 * failure, 3 = transcoding failure.
 */
package org.starhe;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.Comparator;
import java.util.List;
import org.dcm4che3.data.Attributes;
import org.dcm4che3.data.Tag;
import org.dcm4che3.img.DicomImageReader;
import org.dcm4che3.img.DicomImageReaderSpi;
import org.dcm4che3.img.ImageTranscodeParam;
import org.dcm4che3.img.Transcoder;
import org.dcm4che3.img.Transcoder.Format;
import org.dcm4che3.img.stream.DicomFileInputStream;

public final class Dcm2Png {

  private Dcm2Png() {}

  public static void main(String[] args) {
    if (args.length < 2) {
      System.err.println("Usage: Dcm2Png <input.dcm> <output_dir>");
      System.exit(1);
    }

    Path input = Paths.get(args[0]);
    Path outDir = Paths.get(args[1]);

    if (!Files.exists(input) || !Files.isRegularFile(input)) {
      System.err.println("Input file not found or not a file: " + input);
      System.exit(1);
    }

    try {
      Files.createDirectories(outDir);
    } catch (IOException e) {
      System.err.println("Cannot create output directory: " + e.getMessage());
      System.exit(1);
    }

    // ── Load native OpenCV library ────────────────────────────────────────
    // java.library.path must point to the directory containing
    // libopencv_java4130.dylib / libopencv_java4130.so / opencv_java4130.dll
    try {
      System.loadLibrary("opencv_java4130");
    } catch (UnsatisfiedLinkError e) {
      System.err.println(
          "[ERROR] Failed to load OpenCV native library 'opencv_java4130'.\n"
              + "        Set -Djava.library.path=<dir> where the native lib lives.\n"
              + "        Cause: "
              + e.getMessage());
      System.exit(2);
    }

    // ── Read FPS from DICOM metadata (FrameTime / CineRate) ───────────────
    double fps = readFps(input);
    System.out.println("fps=" + fps);

    // ── Convert DICOM → PNG (one file per frame, W/L applied) ─────────────
    try {
      var params = new ImageTranscodeParam(Format.PNG);
      // preserveRawImage=false → Window/Level transformations applied.
      // This is Weasis's default rendering mode (display-ready, 8-bit output).
      params.setPreserveRawImage(false);

      List<Path> outputs = Transcoder.dcm2image(input, outDir, params);

      // Sort by the -NNNNN suffix so the order is always deterministic
      outputs.sort(Comparator.comparing(p -> p.getFileName().toString()));

      System.out.println("frames=" + outputs.size());
      for (Path p : outputs) {
        System.out.println("frame=" + p.toAbsolutePath());
      }

    } catch (Exception e) {
      System.err.println("[ERROR] Transcoding failed: " + e.getMessage());
      e.printStackTrace(System.err);
      System.exit(3);
    }
  }

  // ── Helpers ───────────────────────────────────────────────────────────────

  /**
   * Reads the frame rate from DICOM FrameTime (0018,1063) or CineRate
   * (0018,0040). Falls back to 22 fps if neither tag is present.
   */
  private static double readFps(Path dicomPath) {
    try {
      var spi = new DicomImageReaderSpi();
      var reader = new DicomImageReader(spi);
      try {
        reader.setInput(new DicomFileInputStream(dicomPath));
        Attributes attrs = reader.getStreamMetadata().getDicomObject();

        // FrameTime (ms per frame)
        float frameTime = attrs.getFloat(Tag.FrameTime, 0f);
        if (frameTime > 0f) {
          return Math.round(1000.0 / frameTime * 1000.0) / 1000.0;
        }

        // CineRate (fps direct)
        int cineRate = attrs.getInt(Tag.CineRate, 0);
        if (cineRate > 0) {
          return cineRate;
        }
      } finally {
        reader.dispose();
      }
    } catch (Exception e) {
      System.err.println("[WARN] Could not read FPS from DICOM: " + e.getMessage());
    }
    return 22.0;
  }
}
