import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";

import {
  correctPlate,
  getInspection,
  plateImageUrl,
  processVideo,
  uploadVideo,
  scanImage,
  detectPlate,
  verifyPlate,
} from "../services/api.js";

import { formatDate, getErrorMessage } from "../utils/format.js";
import StatusBadge from "../components/StatusBadge.jsx";
import Message from "../components/Message.jsx";

const SCAN_LIMIT_MS = 60_000;
const DETECT_INTERVAL_MS = 40;         // pause between preview checks (each check also waits for the server)
const DETECT_WIDTH = 800;              // preview frame width (small = fast)
const MAX_CAPTURE_WIDTH = 1920;        // the photo that is read by OCR is full quality
const CONFIRM_READS = 2;               // a doubtful reading must come out the same in this many photos
const MAX_OCR_ATTEMPTS = 10;           // photos that may be read in one scan
const MAX_PARALLEL_OCR = 2;            // photos read at the same time while the camera keeps looking
const MIN_CAPTURE_GAP_MS = 350;        // minimum time between two captured photos
const FINISHED = ["COMPLETED", "NO_PLATE", "FAILED"];

const STATUS_MESSAGE_TYPE = {
  VALID: "success",
  DUE_SOON: "warning",
  EXPIRED: "error",
  OVERDUE: "error",
  FAILED: "error",
  NO_RECORD: "warning",
  NOT_FOUND: "warning",
  NOT_CNG: "info",
  VEHICLE_NOT_FOUND: "warning",
};

function Inspection() {
  const [mode, setMode] = useState("camera");

  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const originalCanvasRef = useRef(null);
  const streamRef = useRef(null);
  const scanTimerRef = useRef(null);
  const scanBusyRef = useRef(false);
  const cameraActiveRef = useRef(false);
  const scanStartedAtRef = useRef(0);
  const previousPlateRef = useRef("");
  const stableCountRef = useRef(0);
  const candidatesRef = useRef({});
  const finishScanRef = useRef(null);
  const ocrAttemptsRef = useRef(0);
  const ocrInFlightRef = useRef(0);
  const lastCaptureAtRef = useRef(0);
  const failuresRef = useRef(0);

  const videoTimerRef = useRef(null);
  const pollingRef = useRef(false);

  const [cameraOn, setCameraOn] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [liveScan, setLiveScan] = useState(null);
  const [verification, setVerification] = useState(null);
  const [manualPlate, setManualPlate] = useState("");
  const [liveStep, setLiveStep] = useState("");
  const [secondsLeft, setSecondsLeft] = useState(60);
  const [bestGuess, setBestGuess] = useState(null);
  const [guide, setGuide] = useState(null); // live "is the plate fully visible" feedback

  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const [step, setStep] = useState("");
  const [result, setResult] = useState(null);
  const [showCorrection, setShowCorrection] = useState(false);

  const stopCamera = useCallback(() => {
    cameraActiveRef.current = false;

    if (scanTimerRef.current) {
      clearTimeout(scanTimerRef.current);
      scanTimerRef.current = null;
    }

    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    }

    if (videoRef.current) {
      videoRef.current.srcObject = null;
    }

    setCameraOn(false);
    setScanning(false);
    setGuide(null);
  }, []);

  useEffect(() => {
    return () => {
      cameraActiveRef.current = false;

      if (scanTimerRef.current) clearTimeout(scanTimerRef.current);
      if (videoTimerRef.current) clearTimeout(videoTimerRef.current);

      if (streamRef.current) {
        streamRef.current.getTracks().forEach((track) => track.stop());
      }
    };
  }, []);

  function changeMode(nextMode) {
    stopCamera();
    setMode(nextMode);
    setError("");
    setSuccess("");
    setLiveScan(null);
    setVerification(null);
    setBestGuess(null);
    setLiveStep("");
  }

  async function startCamera() {
    setError("");
    setSuccess("");
    setLiveScan(null);
    setVerification(null);
    setBestGuess(null);
    setGuide(null);
    setManualPlate("");
    setSecondsLeft(60);
    setLiveStep("Starting camera...");
    previousPlateRef.current = "";
    stableCountRef.current = 0;
    ocrAttemptsRef.current = 0;
    ocrInFlightRef.current = 0;
    lastCaptureAtRef.current = 0;
    failuresRef.current = 0;
    candidatesRef.current = {};
    scanStartedAtRef.current = 0;

    if (
      !navigator.mediaDevices ||
      !navigator.mediaDevices.getUserMedia
    ) {
      setError(
        "Camera access is unavailable. Use HTTPS or localhost, or upload a video."
      );
      setLiveStep("");
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: {
          facingMode: { ideal: "environment" },
          width: { ideal: 1920 },
          height: { ideal: 1080 },
        },
        audio: false,
      });

      streamRef.current = stream;

      if (!videoRef.current) {
        stream.getTracks().forEach((track) => track.stop());
        streamRef.current = null;
        setLiveStep("");
        return;
      }

      videoRef.current.srcObject = stream;
      await videoRef.current.play();

      cameraActiveRef.current = true;
      scanStartedAtRef.current = Date.now();
      setCameraOn(true);
      setLiveStep(
        "Show the number plate to the camera. The photo is taken automatically once the whole plate is clear."
      );
    } catch (err) {
      stopCamera();
      setError(
        err?.name === "NotAllowedError"
          ? "Camera permission was denied. Allow camera access in browser settings."
          : "The camera could not start. Check the connection or upload a video."
      );
      setLiveStep("");
    }
  }

  // Keep the best OCR reading seen across all frames.
  function rememberCandidate(data) {
    const raw = (data?.plateNumber || "").toUpperCase();
    const plate = raw.replace(/[^A-Z0-9]/g, "");

    if (!plate) return null;

    const validFormat = Boolean(data.plateFormatValid);
    const confidenceOkay = !data.lowConfidence;

    // Valid format matters most. Confidence helps rank competing readings.
    const score =
      (validFormat ? 5 : 0) +
      (confidenceOkay ? 2 : 0) +
      Math.min(1, plate.length / 10);

    const previous = candidatesRef.current[plate];

    candidatesRef.current[plate] = {
      plate,
      score: (previous?.score || 0) + score,
      validFormat: validFormat || Boolean(previous?.validFormat),
      lastData: data,
      hits: (previous?.hits || 0) + 1,
    };

    const best = Object.values(candidatesRef.current).sort(
      (a, b) => b.score - a.score
    )[0];

    setBestGuess(best || null);

    return {
      plate,
      validFormat,
      data,
      hits: candidatesRef.current[plate].hits,
    };
  }

  function frameToBlob(canvas, quality = 0.92) {
    return new Promise((resolve) => {
      canvas.toBlob(resolve, "image/jpeg", quality);
    });
  }

  // Draw a picture (a frozen snapshot or the live video) onto a canvas, shrunk to maxWidth if it is wider.
  function drawFrame(source, sourceWidth, sourceHeight, canvas, maxWidth) {
    const scale = Math.min(1, maxWidth / sourceWidth);
    canvas.width = Math.round(sourceWidth * scale);
    canvas.height = Math.round(sourceHeight * scale);
    canvas.getContext("2d").drawImage(source, 0, 0, canvas.width, canvas.height);
  }

  // Stop the camera after the time limit and use the best available candidate.
  const finishScan = useCallback(async () => {
    if (!cameraActiveRef.current) return;

    cameraActiveRef.current = false;

    if (scanTimerRef.current) {
      clearTimeout(scanTimerRef.current);
      scanTimerRef.current = null;
    }

    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    }

    if (videoRef.current) videoRef.current.srcObject = null;

    setCameraOn(false);
    setScanning(false);
    setSecondsLeft(0);

    const candidates = Object.values(candidatesRef.current).sort(
      (a, b) => b.score - a.score
    );

    // Only verify automatically a plate that was read the same way in at least two photos.
    const bestValid = candidates.find(
      (candidate) => candidate.validFormat && candidate.hits >= CONFIRM_READS
    );

    if (bestValid) {
      setManualPlate(bestValid.plate);
      setLiveStep(
        `Time limit reached. Checking the best plate reading: ${bestValid.plate}`
      );

      try {
        const checked = await verifyPlate(bestValid.plate);
        setVerification(checked);
        setSuccess(
          "Scanning finished. Verification was attempted using the best plate reading."
        );
        setLiveStep("Verification result is ready.");
      } catch (err) {
        setError(
          `A possible plate (${bestValid.plate}) was detected, but verification failed: ${getErrorMessage(err)}`
        );
        setLiveStep("Camera stopped. You can retry or verify the plate manually.");
      }

      return;
    }

    // Show the best uncertain guess without claiming it is correct.
    if (candidates.length > 0) {
      const best = candidates[0];
      setManualPlate(best.plate);
      setLiveStep(
        "Time limit reached. OCR found possible text, but could not confirm a valid plate. Please check the number."
      );
      setError(
        "The best OCR reading is only a guess. Correct it below before verifying."
      );
    } else {
      setLiveStep("Time limit reached. No readable plate was detected.");
      setError(
        "No readable number plate was found in 60 seconds. Improve the lighting, move closer, retry, or enter the plate manually."
      );
    }
  }, []);

  // Keep a ref to the latest finish handler for the scan loop.
  useEffect(() => {
    finishScanRef.current = finishScan;
  }, [finishScan]);

  // Stop the camera and show the hydrotest result for a plate.
  const completeWithPlate = useCallback(
    async (plate, data, note) => {
      stopCamera();
      setManualPlate(plate);
      setSecondsLeft(0);
      setLiveStep(`Plate ${plate} captured. Checking hydrotest status...`);

      try {
        const checked = data?.verification || (await verifyPlate(plate));
        setVerification(checked);
        setSuccess(note || "Number plate captured. Verification result is ready.");
        setLiveStep("Verification result is ready.");
      } catch (err) {
        setError(
          `Plate ${plate} was read, but verification failed: ${getErrorMessage(err)}`
        );
        setLiveStep("Camera stopped. You can retry or verify manually.");
      }
    },
    [stopCamera]
  );

  // Read ONE captured photo on the server (crop -> enhance -> OCR -> lookup) while the camera keeps looking.
  const readPhoto = useCallback(
    async (photo) => {
      ocrInFlightRef.current += 1;
      setScanning(true);

      try {
        const data = await scanImage(photo);
        if (!cameraActiveRef.current) return; // the scan already finished

        failuresRef.current = 0;
        setLiveScan(data);
        setError("");

        const candidate = rememberCandidate(data);
        const plate = candidate?.plate || "";

        if (data.plateDetected && plate) {
          // The server only returns a plate that is whole, sharp, complete and checked. A confident reading is
          // final; a doubtful one must come out the same in two photos.
          const confident = Boolean(data.plateFormatValid) && !data.lowConfidence;
          const confirmed = Boolean(data.plateFormatValid) && candidate.hits >= CONFIRM_READS;

          if (confident || confirmed) {
            await completeWithPlate(plate, data);
            return;
          }

          setLiveStep(
            `Read ${plate}, but not sure yet. Waiting for another clear frame to confirm...`
          );
        } else {
          // the server says why it did not accept the photo (blurry, cut off, not clear enough...)
          setLiveStep(
            data.message || "The plate could not be read reliably. Waiting for a clearer frame..."
          );
        }
      } catch (err) {
        failuresRef.current += 1;

        // A missing model / OCR engine will not fix itself: show the real reason and stop.
        if (err?.response?.status === 503 || failuresRef.current >= 5) {
          stopCamera();
          setError(getErrorMessage(err));
          setLiveStep("Camera stopped because the scan service reported a problem.");
        }
      } finally {
        ocrInFlightRef.current -= 1;
        if (ocrInFlightRef.current <= 0) setScanning(false);

        // every photo of this scan has been read and none gave a confirmed plate
        if (
          cameraActiveRef.current &&
          ocrAttemptsRef.current >= MAX_OCR_ATTEMPTS &&
          ocrInFlightRef.current <= 0
        ) {
          await finishScanRef.current?.();
        }
      }
    },
    [completeWithPlate, stopCamera]
  );

  // One round of the live scan. It never waits for anything slow:
  //   1. freeze the picture of THIS instant (a snapshot of the video)
  //   2. send a small copy of it -> is the WHOLE plate visible, big and sharp?
  //   3. if yes, the full-quality version of that SAME snapshot goes to the server to be cropped and read,
  //      while the camera immediately keeps looking for the next clear frame.
  // So a short video needs to be played only once: the photo is taken the moment the plate is good.
  const checkFrame = useCallback(async () => {
    const video = videoRef.current;

    if (
      !cameraActiveRef.current ||
      !video ||
      !video.videoWidth ||
      scanBusyRef.current
    ) {
      return;
    }

    scanBusyRef.current = true;
    let snapshot = null;

    try {
      // ---- 1. freeze this instant ----
      const width = video.videoWidth;
      const height = video.videoHeight;
      snapshot =
        typeof createImageBitmap === "function"
          ? await createImageBitmap(video)
          : null;
      const source = snapshot || video;

      // ---- 2. quick check of a small copy ----
      drawFrame(source, width, height, originalCanvasRef.current, DETECT_WIDTH);
      const previewBlob = await frameToBlob(originalCanvasRef.current, 0.7);
      if (!previewBlob || !cameraActiveRef.current) return;

      const check = await detectPlate(previewBlob, width);
      if (!cameraActiveRef.current) return;

      failuresRef.current = 0;
      setGuide(check);

      // A blurry or partly hidden plate is never captured.
      if (!check.ready) {
        if (ocrInFlightRef.current === 0) {
          setLiveStep(check.message || "Show the number plate to the camera.");
        }
        return;
      }

      // ---- 3. the plate is whole and sharp: take THIS frame at full quality and read it ----
      const now = Date.now();
      if (
        ocrInFlightRef.current >= MAX_PARALLEL_OCR ||
        now - lastCaptureAtRef.current < MIN_CAPTURE_GAP_MS ||
        ocrAttemptsRef.current >= MAX_OCR_ATTEMPTS
      ) {
        return;
      }
      lastCaptureAtRef.current = now;

      drawFrame(source, width, height, canvasRef.current, MAX_CAPTURE_WIDTH);
      const photo = await frameToBlob(canvasRef.current, 0.92);
      if (!photo) return;

      ocrAttemptsRef.current += 1;
      setLiveStep(
        check.lowLight
          ? "Clear plate captured. Low light, so the image is being enhanced and read..."
          : "Clear plate captured. Reading the number..."
      );

      readPhoto(photo); // not awaited: the camera keeps looking while the number is read
    } finally {
      if (snapshot && typeof snapshot.close === "function") snapshot.close();
      scanBusyRef.current = false;
    }
  }, [readPhoto]);

  // Automatic scan loop with a hard 60-second limit.
  useEffect(() => {
    if (!cameraOn || mode !== "camera") return undefined;

    let cancelled = false;

    async function tick() {
      if (cancelled || !cameraActiveRef.current) return;

      const elapsed = Date.now() - scanStartedAtRef.current;
      setSecondsLeft(Math.max(0, Math.ceil((SCAN_LIMIT_MS - elapsed) / 1000)));

      if (elapsed >= SCAN_LIMIT_MS) {
        await finishScanRef.current?.();
        return;
      }

      try {
        await checkFrame();
      } catch (err) {
        failuresRef.current += 1;
        const status = err?.response?.status;

        // A missing model / OCR engine will not fix itself: show the real reason and stop.
        if (status === 503 || failuresRef.current >= 5) {
          stopCamera();
          setError(getErrorMessage(err));
          setLiveStep("Camera stopped because the scan service reported a problem.");
          return;
        }
        setLiveStep("A scan attempt failed. Retrying automatically...");
      }

      if (!cancelled && cameraActiveRef.current) {
        scanTimerRef.current = setTimeout(tick, DETECT_INTERVAL_MS);
      }
    }

    scanTimerRef.current = setTimeout(tick, 200);

    return () => {
      cancelled = true;

      if (scanTimerRef.current) {
        clearTimeout(scanTimerRef.current);
        scanTimerRef.current = null;
      }
    };
  }, [cameraOn, mode, checkFrame, stopCamera]);

  async function checkManualPlate(event) {
    event.preventDefault();

    const plate = manualPlate.toUpperCase().replace(/\s+/g, "");
    if (!plate) return;

    setError("");
    setSuccess("");
    setScanning(true);
    setLiveStep("Checking entered number plate...");

    try {
      stopCamera();

      const checked = await verifyPlate(plate);
      setVerification(checked);
      setManualPlate(plate);
      setLiveStep("Verification result is ready.");
      setSuccess("Vehicle lookup completed.");
    } catch (err) {
      setError(getErrorMessage(err));
      setLiveStep("");
    } finally {
      setScanning(false);
    }
  }

  // ---------------- Video upload mode ----------------

  const pollVideoResult = useCallback(async (id) => {
    if (pollingRef.current) return;
    pollingRef.current = true;

    try {
      const data = await getInspection(id);
      setResult(data);

      if (FINISHED.includes(data.status)) {
        setBusy(false);
        setStep("");
        setManualPlate(data.detectedPlate || "");
        setShowCorrection(data.status === "NO_PLATE");
        pollingRef.current = false;
        return;
      }

      setStep(
        data.progress != null
          ? `Processing video... ${data.progress}%`
          : "Processing video and searching for number plates..."
      );
    } catch (err) {
      setError(getErrorMessage(err));
      setBusy(false);
      setStep("");
      pollingRef.current = false;
      return;
    }

    pollingRef.current = false;
    videoTimerRef.current = setTimeout(() => {
      pollVideoResult(id);
    }, 1500);
  }, []);

  async function analyzeVideo() {
    if (!file || busy) return;

    if (videoTimerRef.current) clearTimeout(videoTimerRef.current);

    setError("");
    setSuccess("");
    setResult(null);
    setShowCorrection(false);
    setBusy(true);
    pollingRef.current = false;

    try {
      setStep("Uploading video...");
      const uploaded = await uploadVideo(file);
      setResult(uploaded);

      setStep("Starting video analysis...");
      await processVideo(uploaded.id);

      setStep("Processing video and detecting number plates...");
      await pollVideoResult(uploaded.id);
    } catch (err) {
      setError(getErrorMessage(err));
      setBusy(false);
      setStep("");
    }
  }

  async function saveCorrection(event) {
    event.preventDefault();

    if (!result?.id || !manualPlate.trim()) return;

    setError("");
    setSuccess("");

    try {
      const updated = await correctPlate(
        result.id,
        manualPlate.trim().toUpperCase()
      );

      setResult(updated);
      setShowCorrection(false);
      setManualPlate(updated.detectedPlate || manualPlate.toUpperCase());
      setSuccess("Number plate updated.");
    } catch (err) {
      setError(getErrorMessage(err));
    }
  }

  const lookup = result?.lookup;
  const videoFinished = result && FINISHED.includes(result.status);
  const vehicle = verification?.vehicle;
  const cylinders = Array.isArray(verification?.cylinders)
    ? verification.cylinders
    : [];

  return (
    <div className="inspection-page">
      <h1>Vehicle Inspection</h1>
      <p>
        Detect number plates in low-light footage and verify the vehicle's
        CNG hydrotest status.
      </p>

      <section className="panel">
        <div className="button-row">
          <button
            type="button"
            className={`button ${mode === "camera" ? "" : "secondary"}`}
            onClick={() => changeMode("camera")}
          >
            Live Camera
          </button>

          <button
            type="button"
            className={`button ${mode === "upload" ? "" : "secondary"}`}
            onClick={() => changeMode("upload")}
          >
            Upload Video
          </button>
        </div>
      </section>

      <Message type="error">{error}</Message>
      <Message type="success">{success}</Message>

      {mode === "camera" && (
        <>
          <section className="panel">
            <h2>Automatic Number Plate Detection</h2>
            <p>
              Show the vehicle (or play its video) to the camera and leave it
              running. The moment the whole number plate is visible, big
              enough and sharp, that exact frame is captured, the plate is
              cropped, enhanced for low light, and read with OCR. A blurry or
              half-visible plate gives no result instead of a wrong one.
              Scanning lasts up to 60 seconds.
            </p>

            <div
              className="camera-box"
              style={{ position: "relative", overflow: "hidden" }}
            >
              <video
                ref={videoRef}
                muted
                playsInline
                autoPlay
                style={{
                  display: cameraOn ? "block" : "none",
                  width: "100%",
                }}
              />

              {!cameraOn && (
                <div className="camera-placeholder">
                  {verification
                    ? "Camera stopped — result ready"
                    : "Camera is off"}
                </div>
              )}

              {cameraOn && (
                <span className="camera-status">
                  {scanning ? "Scanning..." : "Camera active"}
                </span>
              )}

              {cameraOn && (
                <div
                  aria-hidden="true"
                  style={{
                    position: "absolute",
                    ...(guide?.box
                      ? {
                          left: `${guide.box.x * 100}%`,
                          top: `${guide.box.y * 100}%`,
                          width: `${guide.box.w * 100}%`,
                          height: `${guide.box.h * 100}%`,
                        }
                      : { inset: "25% 8%" }),
                    border: `3px solid ${guide?.ready ? "#2e9e5b" : "#f5b942"}`,
                    borderRadius: 10,
                    transition: "all 120ms linear",
                    pointerEvents: "none",
                  }}
                />
              )}
            </div>

            <canvas ref={canvasRef} style={{ display: "none" }} />
            <canvas ref={originalCanvasRef} style={{ display: "none" }} />

            {cameraOn && (
              <div className="progress-box">
                <p>
                  <strong>{secondsLeft} seconds remaining</strong>
                </p>
                <div className="progress">
                  <div
                    className="progress-bar"
                    style={{
                      width: `${((60 - secondsLeft) / 60) * 100}%`,
                    }}
                  />
                </div>
              </div>
            )}

            {liveStep && <p className="hint">{liveStep}</p>}

            {bestGuess && cameraOn && (
              <p className="hint">
                Best current OCR guess: <strong>{bestGuess.plate}</strong>
                {bestGuess.validFormat ? " (valid format)" : " (not confirmed)"}
              </p>
            )}

            <div className="button-row">
              {!cameraOn ? (
                <button
                  type="button"
                  className="button"
                  onClick={startCamera}
                  disabled={scanning}
                >
                  {verification || bestGuess ? "Scan Again" : "Start Camera"}
                </button>
              ) : (
                <button
                  type="button"
                  className="button secondary"
                  onClick={stopCamera}
                >
                  Stop Camera
                </button>
              )}
            </div>
          </section>

          <form className="panel form" onSubmit={checkManualPlate}>
            <h3>Enter or Correct Number Plate</h3>
            <label>
              Vehicle registration number
              <input
                value={manualPlate}
                onChange={(event) => setManualPlate(event.target.value)}
                placeholder="GJ01AB1234"
                required
                minLength={4}
              />
            </label>
            <div className="button-row">
              <button
                type="submit"
                className="button"
                disabled={scanning || !manualPlate.trim()}
              >
                {scanning ? "Checking..." : "Verify Number Plate"}
              </button>
            </div>
          </form>

          {verification && (
            <section className="panel">
              <h2>Hydrotest Verification Result</h2>

              <dl className="details">
                <div>
                  <dt>Number Plate</dt>
                  <dd className="plate-text">
                    {verification.plateNumber || manualPlate || "-"}
                  </dd>
                </div>
                <div>
                  <dt>CNG Hydrotest Status</dt>
                  <dd>
                    <StatusBadge status={verification.status || "NOT_FOUND"} />
                  </dd>
                </div>
              </dl>

              <Message
                type={STATUS_MESSAGE_TYPE[verification.status] || "info"}
              >
                {verification.message ||
                  "Review the verification status and vehicle records below."}
              </Message>

              {vehicle && (
                <>
                  <h3>Vehicle Details</h3>
                  <dl className="details">
                    <div>
                      <dt>Fuel Type</dt>
                      <dd>{vehicle.fuelType || "-"}</dd>
                    </div>
                    <div>
                      <dt>Vehicle Class</dt>
                      <dd>{vehicle.vehicleClass || "-"}</dd>
                    </div>
                    <div>
                      <dt>Make / Model</dt>
                      <dd>{vehicle.makerModel || "-"}</dd>
                    </div>
                    <div>
                      <dt>Owner</dt>
                      <dd>{vehicle.ownerName || "-"}</dd>
                    </div>
                    <div>
                      <dt>Registration Date</dt>
                      <dd>
                        {vehicle.registrationDate
                          ? formatDate(vehicle.registrationDate)
                          : "-"}
                      </dd>
                    </div>
                    <div>
                      <dt>Data Source</dt>
                      <dd>{vehicle.source || "-"}</dd>
                    </div>
                  </dl>
                </>
              )}

              {cylinders.length > 0 && (
                <>
                  <h3>Cylinder Hydrotest Records</h3>
                  <div className="table-scroll">
                    <table>
                      <thead>
                        <tr>
                          <th>Cylinder Serial</th>
                          <th>Last Test</th>
                          <th>Next Due</th>
                          <th>Days to Due</th>
                          <th>Result</th>
                          <th>Status</th>
                        </tr>
                      </thead>
                      <tbody>
                        {cylinders.map((cylinder, index) => (
                          <tr
                            key={cylinder.cylinderSerial || `cylinder-${index}`}
                          >
                            <td>{cylinder.cylinderSerial || "-"}</td>
                            <td>{formatDate(cylinder.lastTestDate)}</td>
                            <td>{formatDate(cylinder.nextDueDate)}</td>
                            <td>{cylinder.daysToDue ?? "-"}</td>
                            <td>{cylinder.result || "-"}</td>
                            <td>
                              <StatusBadge
                                status={cylinder.status || "NO_RECORD"}
                              />
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </>
              )}

              <div className="button-row">
                <button
                  type="button"
                  className="button secondary"
                  onClick={() => {
                    setVerification(null);
                    setLiveScan(null);
                    setBestGuess(null);
                    setManualPlate("");
                    setSuccess("");
                    setError("");
                    setLiveStep("");
                  }}
                >
                  Clear Result
                </button>

                <Link
                  className="button secondary"
                  to={`/cng?plate=${encodeURIComponent(
                    verification.plateNumber || manualPlate
                  )}`}
                >
                  Open CNG Verification
                </Link>
              </div>
            </section>
          )}
        </>
      )}

      {mode === "upload" && (
        <>
          <section className="panel">
            <h2>Upload Inspection Video</h2>
            <p>
              Upload an MP4, AVI, MOV, or MKV video to detect the number plate
              and look up the matching asset.
            </p>

            <label className="file-picker">
              Select Video
              <input
                type="file"
                accept=".mp4,.avi,.mov,.mkv,video/*"
                disabled={busy}
                onChange={(event) => {
                  setFile(event.target.files?.[0] || null);
                  setResult(null);
                  setError("");
                  setSuccess("");
                }}
              />
            </label>

            {file && (
              <p>
                Selected: <strong>{file.name}</strong>
              </p>
            )}

            <button
              type="button"
              className="button"
              onClick={analyzeVideo}
              disabled={!file || busy}
            >
              {busy ? "Processing..." : "Upload & Analyze"}
            </button>

            {busy && (
              <div className="progress-box">
                <p>{step}</p>
                {result?.status === "PROCESSING" && (
                  <div className="progress">
                    <div
                      className="progress-bar"
                      style={{
                        width: `${Math.min(
                          100,
                          Math.max(0, result.progress || 0)
                        )}%`,
                      }}
                    />
                  </div>
                )}
              </div>
            )}
          </section>

          {videoFinished && result.status === "FAILED" && (
            <Message type="error">
              {result.message || "The video could not be processed."}
            </Message>
          )}

          {videoFinished && result.status === "NO_PLATE" && (
            <Message type="warning">
              {result.message ||
                "No number plate was found. Enter the plate manually below."}
            </Message>
          )}

          {videoFinished && result.status === "COMPLETED" && (
            <section className="panel">
              <h2>Video Inspection Result</h2>

              {result.lowConfidence && (
                <Message type="warning">
                  {result.message ||
                    "The detected number plate has low confidence. Check it before relying on the result."}
                </Message>
              )}

              <div className="result-grid">
                {result.hasPlateImage && (
                  <div>
                    <p className="label">Cropped Plate Image</p>
                    <img
                      className="plate-image"
                      src={plateImageUrl(result.id)}
                      alt="Cropped detected number plate"
                    />
                  </div>
                )}

                <dl className="details">
                  <div>
                    <dt>Detected Number Plate</dt>
                    <dd className="plate-text">
                      {result.detectedPlate || "-"}
                    </dd>
                  </div>

                  {result.rawText && !result.manuallyCorrected && (
                    <div>
                      <dt>Raw OCR Text</dt>
                      <dd>{result.rawText}</dd>
                    </div>
                  )}

                  {result.confidence != null && !result.manuallyCorrected && (
                    <div>
                      <dt>OCR Confidence</dt>
                      <dd>{Math.round(result.confidence * 100)}%</dd>
                    </div>
                  )}

                  {result.manuallyCorrected && (
                    <div>
                      <dt>Source</dt>
                      <dd>Entered manually</dd>
                    </div>
                  )}

                  <div>
                    <dt>Hydrotest Status</dt>
                    <dd>
                      <StatusBadge
                        status={lookup?.hydrotestStatus || "NOT_FOUND"}
                      />
                    </dd>
                  </div>

                  {lookup?.asset && (
                    <>
                      <div>
                        <dt>Asset</dt>
                        <dd>
                          {lookup.asset.assetId} ({lookup.asset.assetType},{" "}
                          {lookup.asset.station})
                        </dd>
                      </div>
                      <div>
                        <dt>Last Test</dt>
                        <dd>{formatDate(lookup.asset.testDate)}</dd>
                      </div>
                      <div>
                        <dt>Next Due</dt>
                        <dd>{formatDate(lookup.asset.nextDueDate)}</dd>
                      </div>
                    </>
                  )}
                </dl>
              </div>

              {lookup && !lookup.found && (
                <Message type="warning">
                  No asset is registered with number{" "}
                  {lookup.plateNumber || result.detectedPlate}. Check the
                  number or <Link to="/assets/new">add a new asset</Link>.
                </Message>
              )}

              <div className="button-row">
                {lookup?.asset && (
                  <Link
                    className="button"
                    to={`/assets/${lookup.asset.assetId}`}
                  >
                    View Asset
                  </Link>
                )}

                <Link
                  className="button secondary"
                  to={`/cng?plate=${encodeURIComponent(
                    result.detectedPlate || ""
                  )}`}
                >
                  Verify CNG Hydrotest
                </Link>

                <button
                  type="button"
                  className="button secondary"
                  onClick={() => setShowCorrection((value) => !value)}
                >
                  Correct Number Plate
                </button>
              </div>
            </section>
          )}

          {videoFinished &&
            result.status !== "FAILED" &&
            showCorrection && (
              <form className="panel form" onSubmit={saveCorrection}>
                <h3>Correct Number Plate</h3>
                <label>
                  Enter the correct registration number
                  <input
                    value={manualPlate}
                    onChange={(event) =>
                      setManualPlate(event.target.value.toUpperCase())
                    }
                    placeholder="GJ01AB1234"
                    required
                    minLength={3}
                  />
                </label>
                <div className="button-row">
                  <button type="submit" className="button">
                    Search Asset
                  </button>
                </div>
              </form>
            )}
        </>
      )}
    </div>
  );
}

export default Inspection;