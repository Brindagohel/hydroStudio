import { useCallback, useEffect, useRef, useState } from "react";
import { scanFrame } from "../services/api.js";
import { getErrorMessage } from "../utils/format.js";
import Message from "./Message.jsx";

const MAX_SECONDS = 20;   // stop looking after this long
const FRAME_GAP_MS = 400; // pause between frames

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
// a result that looks like a real plate beats a higher-confidence guess that doesn't
const score = (r) => (r.ocrConfidence || 0) + (r.plateFormatValid ? 1 : 0);

function CameraCapture({ onResult }) {
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const streamRef = useRef(null);
  const stopRef = useRef(false);

  const [cameraOn, setCameraOn] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");

  const stopCamera = useCallback(() => {
    stopRef.current = true;
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
    if (videoRef.current) videoRef.current.srcObject = null;
    setCameraOn(false);
  }, []);

  useEffect(() => stopCamera, [stopCamera]); // release camera when leaving

  async function startCamera() {
    setError("");
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      setError("This browser cannot open the camera. Camera needs HTTPS (or localhost).");
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: { ideal: "environment" }, width: { ideal: 1280 }, height: { ideal: 720 } },
        audio: false,
      });
      streamRef.current = stream;
      videoRef.current.srcObject = stream;
      await videoRef.current.play();
      stopRef.current = false;
      setCameraOn(true);
    } catch (err) {
      stopCamera();
      setError(
        err && err.name === "NotAllowedError"
          ? "Camera permission was denied. Allow camera access in the browser."
          : "The camera could not be started. Check that no other app is using it."
      );
    }
  }

  function grabFrame() {
    const video = videoRef.current;
    if (!video || !video.videoWidth) return Promise.resolve(null);
    const canvas = canvasRef.current;
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext("2d").drawImage(video, 0, 0);
    return new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.9));
  }

  async function startScan() {
    setError("");
    stopRef.current = false;
    setScanning(true);
    const started = Date.now();
    let best = null;
    let tries = 0;
    let lastText = "";
    let repeats = 0;

    try {
      while (!stopRef.current && Date.now() - started < MAX_SECONDS * 1000) {
        const blob = await grabFrame();
        if (!blob) { await sleep(FRAME_GAP_MS); continue; }

        tries += 1;
        setStatus(`Checking frame ${tries}...`);
        const r = await scanFrame(blob, false);

        if (r.plateDetected) {
          if (!best || score(r) > score(best.reading)) best = { blob, reading: r };
          // stop early when the same confident, valid-looking plate is read twice
          if (r.plateFormatValid && !r.lowConfidence) {
            repeats = r.plateNumber === lastText ? repeats + 1 : 0;
            lastText = r.plateNumber;
            if (repeats >= 1) break;
          }
        }
        await sleep(FRAME_GAP_MS);
      }

      if (!best) {
        if (!stopRef.current) setError("No number plate was found. Hold the camera steady, closer to the plate, and try again.");
        return;
      }

      setStatus("Reading the best frame...");
      const saved = await scanFrame(best.blob, true); // store the best frame as an inspection
      if (saved.inspection) {
        onResult(saved.inspection);
        stopCamera();
      } else {
        setError(saved.message || "The plate could not be read. Try again.");
      }
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setScanning(false);
      setStatus("");
    }
  }

  return (
    <section className="panel">
      <div className="camera-box">
        <video ref={videoRef} muted playsInline style={{ display: cameraOn ? "block" : "none" }} />
        {!cameraOn && <div className="camera-placeholder">Camera is off</div>}
        {cameraOn && <span className="camera-status">{scanning ? status || "Scanning..." : "Ready"}</span>}
      </div>
      <canvas ref={canvasRef} style={{ display: "none" }} />

      <div className="button-row">
        {!cameraOn ? (
          <button className="button" onClick={startCamera}>Start Camera</button>
        ) : (
          <>
            <button className="button" onClick={startScan} disabled={scanning}>
              {scanning ? "Scanning..." : "Start Scanning"}
            </button>
            {scanning && <button className="button secondary" onClick={() => { stopRef.current = true; }}>Cancel</button>}
            <button className="button secondary" onClick={stopCamera} disabled={scanning}>Stop Camera</button>
          </>
        )}
      </div>
      <Message type="error">{error}</Message>
    </section>
  );
}

export default CameraCapture;