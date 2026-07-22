/**
 * afterPack.js — electron-builder hook (macOS): ad-hoc sign the whole .app.
 *
 * Builds are unsigned (no Apple Developer ID / CSC_IDENTITY_AUTO_DISCOVERY=false),
 * so electron-builder leaves the bundle WITHOUT a `Contents/_CodeSignature` seal.
 * Only the inner Electron binary keeps its own linker-signed ad-hoc signature,
 * which does not cover the resources we add (starhe_worker, jre, weasis-dcm2png,
 * go_server). macOS then fails the Gatekeeper assessment with:
 *
 *   "code has no resources but signature indicates they must be present"
 *
 * …and refuses to open the downloaded app ("STARHE is damaged").
 *
 * Ad-hoc signing the bundle here (before the .dmg/.zip are produced) gives a
 * coherent seal over everything. The app is still not Developer-ID signed nor
 * notarized, so first launch shows the normal "unidentified developer" prompt
 * (right-click → Open) instead of the misleading "damaged" error.
 */
const { execFileSync } = require('child_process');
const path = require('path');

exports.default = async function afterPack(context) {
  if (context.electronPlatformName !== 'darwin') return;

  const appName = `${context.packager.appInfo.productFilename}.app`;
  const appPath = path.join(context.appOutDir, appName);

  console.log(`[afterPack] ad-hoc signing ${appPath}`);
  try {
    // --deep so nested binaries (worker, jre, go_server) are covered too.
    execFileSync('codesign', ['--force', '--deep', '--sign', '-', appPath], {
      stdio: 'inherit',
    });
    execFileSync('codesign', ['--verify', '--strict', '--verbose=1', appPath], {
      stdio: 'inherit',
    });
    console.log('[afterPack] ad-hoc signature OK');
  } catch (err) {
    // Don't fail the build: an unsigned bundle still works after the user runs
    // `xattr -rd com.apple.quarantine`, so surface the problem without blocking.
    console.warn(`[afterPack] ad-hoc signing failed: ${err.message}`);
  }
};
