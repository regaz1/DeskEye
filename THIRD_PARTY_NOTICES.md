# DeskEye 0.3 — Third-party notices

The `licenses` directory preserves the unmodified license/copyright/notice files
provided by the installed wheels used for this build. Keep this directory with
the distribution. `licenses/BUILD-INVENTORY.txt` lists exact versions, including
build tools (not every build tool is part of the runtime).

Main components include Python (PSF), Tcl/Tk, MediaPipe (Apache-2.0), OpenCV
(Apache-2.0 with additional bundled-library notices), NumPy (BSD and bundled
numerical-library licenses), Pillow (MIT-CMU and bundled codec licenses),
Matplotlib, and PyInstaller (GPL with its bootloader distribution exception).
The actual included license texts govern; these summaries do not replace them.
No affiliation or endorsement by Google, Sony, Microsoft or these projects is implied.

## Models

The unchanged Google MediaPipe float16 version-1 task bundles are included:

- `hand_landmarker.task`: `fbc2a30080c3c557093b5ddfc334698132eb341044ccee322ccf8bcf3607cde1`
- `face_landmarker.task`: `64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff`

Source: `https://storage.googleapis.com/mediapipe-models/{task}/{task}/float16/1/{task}.task`.
The MediaPipe authors' Apache-2.0 text is retained under `licenses/mediapipe`.
Google's [hand tracking model card](https://storage.googleapis.com/mediapipe-assets/Model%20Card%20Hand%20Tracking%20%28Lite_Full%29%20with%20Fairness%20Oct%202021.pdf)
and [Face Mesh V2 model card](https://storage.googleapis.com/mediapipe-assets/Model%20Card%20MediaPipe%20Face%20Mesh%20V2.pdf)
identify Apache License 2.0 and explain model limits.

## Data processing

DeskEye does not record camera frames or send them to its own service. Google
states that MediaPipe Tasks processes input on-device and sends performance and
utilization metrics to Google. The app displays this information before tracking
is first enabled. See the [MediaPipe Tasks privacy notice](https://developers.google.com/edge/mediapipe/solutions/tasks#mediapipe-tasks-privacy-notice).

## DeskEye artwork

The logo was supplied by the project owner. Its checkerboard background was
removed using the built-in imagegen edit tool; the result was converted to the
Windows ICO format. See `assets/PROVENANCE.md` in the source project. Third-party
licenses above do not grant rights to the DeskEye branding or to the original
project code. No open-source license has yet been selected for that code.
