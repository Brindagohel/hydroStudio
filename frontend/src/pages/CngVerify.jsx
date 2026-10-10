
import { useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import Message from "../components/Message.jsx";
import StatusBadge from "../components/StatusBadge.jsx";
import { scanImage, verifyPlate } from "../services/api.js";
import { formatDate, getErrorMessage } from "../utils/format.js";

const STATUS_MESSAGE_TYPE = {
  VALID: "success",
  DUE_SOON: "warning",
  EXPIRED: "error",
  FAILED: "error",
  NO_RECORD: "warning",
  NOT_CNG: "info",
  VEHICLE_NOT_FOUND: "warning",
};

function CngVerify() {
  const [params] = useSearchParams();

  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const streamRef = useRef(null);
  const busyRef = useRef(false);

  const [cameraOn, setCameraOn] = useState(false);
  const [autoScan, setAutoScan] = useState(true);
  const [scanRound, setScanRound] = useState(0);
  const [scanning, setScanning] = useState(false);
  const [error, setError] = useState("");
  const [scan, setScan] = useState(null);
  const [verification, setVerification] = useState(null);
  const [manualPlate, setManualPlate] = useState("");

  const stopCamera = useCallback(() => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    }

    if (videoRef.current) {
      videoRef.current.srcObject = null;
    }

    setCameraOn(false);
  }, []);

  useEffect(() => {
    return () => stopCamera();
  }, [stopCamera]);

  async function startCamera() {
    setError("");

    if (
      !navigator.mediaDevices ||
      !navigator.mediaDevices.getUserMedia
    ) {
      setError(
        "Camera access is not available in this browser. Use HTTPS or localhost, or upload a photo instead."
      );
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: {
          facingMode: { ideal: "environment" },
          width: { ideal: 1280 },
          height: { ideal: 720 },
        },
        audio: false,
      });

      streamRef.current = stream;

      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
      }

      setCameraOn(true);
    } catch (err) {
      stopCamera();

      setError(
        err?.name === "NotAllowedError"
          ? "Camera permission was denied. Allow camera access in your browser, or upload a photo instead."
          : "The camera could not be started. Check your camera connection or upload a photo instead."
      );
    }
  }

  const submitImage = useCallback(async (blob) => {
    try {
      const data = await scanImage(blob);

      setScan(data);
      setVerification(data.verification || null);

      if (data.plateNumber) {
        setManualPlate(data.plateNumber.toUpperCase());
      }

      setError("");

      return Boolean(
        data.plateDetected &&
        data.plateFormatValid &&
        !data.lowConfidence &&
        data.verification
      );
    } catch (err) {
      setError(getErrorMessage(err));
      return true;
    }
  }, []);

  const captureAndScan = useCallback(async () => {
    const video = videoRef.current;
    const canvas = canvasRef.current;

    if (
      !video ||
      !canvas ||
      !video.videoWidth ||
      busyRef.current
    ) {
      return false;
    }

    busyRef.current = true;
    setScanning(true);

    try {
      canvas.width = video.videoWidth;
      canvas.height = video.videoHeight;

      const context = canvas.getContext("2d");

      if (!context) {
        setError("Unable to capture the camera frame. Please try again.");
        return true;
      }

      context.drawImage(video, 0, 0);

      const blob = await new Promise((resolve) => {
        canvas.toBlob(resolve, "image/jpeg", 0.9);
      });

      if (!blob) {
        setError("Unable to capture an image. Please try again.");
        return true;
      }

      return await submitImage(blob);
    } finally {
      busyRef.current = false;
      setScanning(false);
    }
  }, [submitImage]);

  useEffect(() => {
    if (!cameraOn || !autoScan) return undefined;

    let cancelled = false;
    let timer;

    const tick = async () => {
      const done = await captureAndScan();

      if (!done && !cancelled) {
        timer = setTimeout(tick, 2500);
      }
    };

    timer = setTimeout(tick, 1000);

    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [cameraOn, autoScan, scanRound, captureAndScan]);

  async function uploadPhoto(event) {
    const file = event.target.files?.[0];
    event.target.value = "";

    if (!file) return;

    setError("");
    setScanning(true);

    try {
      await submitImage(file);
    } finally {
      setScanning(false);
    }
  }

  const checkPlate = useCallback(async (plate) => {
    const normalizedPlate = plate.trim().toUpperCase();

    if (!normalizedPlate) {
      setError("Please enter a vehicle registration number.");
      return;
    }

    setError("");
    setScanning(true);

    try {
      const data = await verifyPlate(normalizedPlate);
      setVerification(data);
      setScan(null);
      setManualPlate(normalizedPlate);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setScanning(false);
    }
  }, []);

  useEffect(() => {
    const plate = params.get("plate");

    if (plate) {
      setManualPlate(plate.toUpperCase());
      checkPlate(plate);
    }
  }, [params, checkPlate]);

  function submitManual(event) {
    event.preventDefault();
    checkPlate(manualPlate);
  }

  const vehicle = verification?.vehicle;
  const cylinders = verification?.cylinders || [];

  return (
    <main className="scanner-page">
      {/* HERO */}
      <section className="scanner-hero">
        <div className="scanner-hero-copy">
          <div className="scanner-eyebrow">
            <span className="live-dot" />
            INTELLIGENT VEHICLE VERIFICATION
          </div>

          <h1>
            Every vehicle.
            <br />
            <span>One smart scan.</span>
          </h1>

          <p>
            Scan a registration plate, identify the vehicle, and check
            CNG cylinder hydrotest validity through your verification system.
          </p>

          <div className="scanner-feature-list">
            <span>
              <span className="feature-icon">⌗</span>
              Plate recognition
            </span>
            <span>
              <span className="feature-icon">◈</span>
              Vehicle lookup
            </span>
            <span>
              <span className="feature-icon">✓</span>
              Hydrotest check
            </span>
          </div>
        </div>

        <div className="scanner-orbit-art" aria-hidden="true">
          <div className="orbit orbit-one" />
          <div className="orbit orbit-two" />
          <div className="orbit-core">⌗</div>
          <span className="orbit-chip chip-top">AI VISION</span>
          <span className="orbit-chip chip-bottom">CNG CHECK</span>
          <span className="orbit-spark spark-one">✦</span>
          <span className="orbit-spark spark-two">✧</span>
        </div>
      </section>

      {/* CAMERA SECTION TITLE */}
      <div className="scanner-section-heading">
        <div>
          <span className="section-kicker">LIVE DETECTION</span>
          <h2>Camera scanner</h2>
          <p>
            Position the number plate inside the scanning frame.
          </p>
        </div>

        <div className={`scanner-live-pill ${cameraOn ? "is-live" : ""}`}>
          <span className="live-dot" />
          {cameraOn ? "CAMERA LIVE" : "CAMERA STANDBY"}
        </div>
      </div>

      {/* CAMERA WORKSPACE */}
      <section className="scanner-workspace">
        <div className="scanner-camera-card">
          <div className="scanner-camera-topbar">
            <div className="camera-title">
              <span className="camera-title-icon">◉</span>
              <div>
                <strong>Vision Studio</strong>
                <small>Registration plate detection</small>
              </div>
            </div>

            <span className="camera-mode-tag">
              {cameraOn ? "● LIVE FEED" : "○ STANDBY"}
            </span>
          </div>

          <div
            className={`scanner-viewport ${
              cameraOn ? "camera-active" : ""
            }`}
          >
            <video
              ref={videoRef}
              muted
              playsInline
              style={{ display: cameraOn ? "block" : "none" }}
            />

            {!cameraOn && (
              <div className="scanner-placeholder">
                <div className="placeholder-camera-icon">⌑</div>
                <h3>Your camera view starts here</h3>
                <p>
                  Enable your camera to begin vehicle number-plate scanning.
                </p>
                <span className="placeholder-hint">
                  CAMERA ACCESS REQUIRED
                </span>
              </div>
            )}

            {cameraOn && (
              <>
                <div className="scanner-grid-overlay" />

                <div className="scan-frame">
                  <i className="frame-corner corner-tl" />
                  <i className="frame-corner corner-tr" />
                  <i className="frame-corner corner-bl" />
                  <i className="frame-corner corner-br" />

                  {autoScan && <div className="animated-scan-line" />}

                  <span className="frame-label">
                    PLACE NUMBER PLATE HERE
                  </span>
                </div>

                <div className="viewport-top-label">
                  VISION FEED / 01
                </div>

                <div className="viewport-bottom-label">
                  <span className="live-dot" />
                  {scanning
                    ? "ANALYZING FRAME..."
                    : autoScan
                      ? "AUTO-SCAN ENABLED"
                      : "READY TO CAPTURE"}
                </div>

                <div className="viewport-crosshair">+</div>
              </>
            )}
          </div>

          <canvas ref={canvasRef} style={{ display: "none" }} />

          <div className="scanner-camera-controls">
            {!cameraOn ? (
              <button
                type="button"
                className="button scanner-primary-button"
                onClick={startCamera}
              >
                <span>◉</span> Start Camera
              </button>
            ) : (
              <>
                <button
                  type="button"
                  className="button scanner-primary-button"
                  onClick={captureAndScan}
                  disabled={scanning}
                >
                  <span>⌗</span>
                  {scanning ? "Scanning..." : "Capture & Check"}
                </button>

                <button
                  type="button"
                  className="button scanner-secondary-button"
                  onClick={() => setScanRound((n) => n + 1)}
                  disabled={scanning || !autoScan}
                >
                  ↻ Scan Again
                </button>

                <button
                  type="button"
                  className="button scanner-stop-button"
                  onClick={stopCamera}
                >
                  ■ Stop
                </button>
              </>
            )}

            <label className="button scanner-upload-button">
              ↑ Upload Photo
              <input
                type="file"
                accept="image/*"
                capture="environment"
                onChange={uploadPhoto}
                hidden
              />
            </label>
          </div>

          <div className="scanner-camera-footer">
            <label className="scanner-toggle">
              <input
                type="checkbox"
                checked={autoScan}
                onChange={(event) => setAutoScan(event.target.checked)}
              />
              <span className="toggle-track">
                <span />
              </span>
              <span>Auto-scan frames</span>
            </label>

            <span className="camera-footer-note">
              JPG · PNG · WEBP
            </span>
          </div>
        </div>

        {/* SCANNING PIPELINE */}
        <aside className="scanner-side-panel">
          <div className="scanner-side-heading">
            <span className="side-heading-icon">✧</span>
            <div>
              <h3>Detection pipeline</h3>
              <p>From image to verification</p>
            </div>
          </div>

          <div className="pipeline-list">
            <div className="pipeline-step">
              <div className="pipeline-icon">◉</div>
              <div>
                <strong>01 · Capture</strong>
                <span>Read the vehicle image</span>
              </div>
              <span className="pipeline-check">✓</span>
            </div>

            <div className="pipeline-connector" />

            <div className="pipeline-step">
              <div className="pipeline-icon">⌗</div>
              <div>
                <strong>02 · Recognize</strong>
                <span>Read the registration plate</span>
              </div>
              <span className="pipeline-check">✓</span>
            </div>

            <div className="pipeline-connector" />

            <div className="pipeline-step">
              <div className="pipeline-icon">◇</div>
              <div>
                <strong>03 · Verify</strong>
                <span>Check vehicle and test data</span>
              </div>
              <span className="pipeline-check">✓</span>
            </div>
          </div>

          <div className="scanner-tip">
            <span className="tip-icon">✦</span>
            <div>
              <strong>For the best scan</strong>
              <p>
                Keep the number plate clearly visible, well-lit, and
                inside the corner guides.
              </p>
            </div>
          </div>

          <div className="scanner-mini-status">
            <span className="mini-status-icon">◎</span>
            <div>
              <strong>Camera privacy</strong>
              <span>The camera is stopped when you leave this page.</span>
            </div>
          </div>
        </aside>
      </section>

      {/* SCAN MESSAGES */}
      <Message type="error">{error}</Message>

      {scan && !scan.plateDetected && (
        <Message type="info">{scan.message}</Message>
      )}

      {scan && scan.plateDetected && scan.lowConfidence && (
        <Message type="warning">{scan.message}</Message>
      )}

      {scan && scan.plateDetected && !scan.plateFormatValid && (
        <Message type="warning">
          The text read ({scan.plateNumber}) does not look like a
          standard registration number. Please check it below.
        </Message>
      )}

      {scan &&
        scan.plateDetected &&
        !scan.verification &&
        scan.message &&
        !scan.lowConfidence && (
          <Message type="warning">{scan.message}</Message>
        )}

      {/* MANUAL VEHICLE SEARCH */}
      <form className="manual-lookup-card" onSubmit={submitManual}>
        <div className="manual-lookup-icon">⌕</div>

        <div className="manual-lookup-copy">
          <span className="section-kicker">MANUAL SEARCH</span>
          <h3>Prefer to enter the plate?</h3>
          <p>
            Enter a registration number to verify a vehicle without
            using the camera.
          </p>
        </div>

        <div className="manual-lookup-input">
          <label htmlFor="manual-plate">
            Vehicle registration number
          </label>
          <input
            id="manual-plate"
            value={manualPlate}
            onChange={(event) =>
              setManualPlate(event.target.value.toUpperCase())
            }
            placeholder="GJ01AB1001"
            required
            minLength={4}
          />
        </div>

        <button
          className="button scanner-primary-button"
          type="submit"
          disabled={scanning}
        >
          {scanning ? "Checking..." : "Verify Vehicle →"}
        </button>
      </form>

      {/* VERIFICATION RESULTS */}
      {verification && (
        <section className="verification-result-card">
          <div className="result-card-heading">
            <div>
              <span className="section-kicker">
                VERIFICATION REPORT
              </span>
              <h2>Vehicle check results</h2>
              <p>
                Review the vehicle information and hydrotest status returned
                by your verification service.
              </p>
            </div>
            <span className="result-shield">✓</span>
          </div>

          <div className="verification-summary">
            <div className="verified-plate-card">
              <span>REGISTRATION NUMBER</span>
              <strong>{verification.plateNumber || manualPlate || "-"}</strong>
              <small>Vehicle identity</small>
            </div>

            <div className="verified-status-card">
              <span>HYDROTEST STATUS</span>
              <StatusBadge status={verification.status} />
              <small>Verification result</small>
            </div>
          </div>

          <Message
            type={STATUS_MESSAGE_TYPE[verification.status] || "info"}
          >
            {verification.message}
          </Message>

          {vehicle && (
            <div className="verification-detail-section">
              <div className="verification-subheading">
                <span>◈</span>
                <h3>Vehicle information</h3>
              </div>

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
                  <dt>Registered On</dt>
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
            </div>
          )}

          {cylinders.length > 0 && (
            <div className="verification-detail-section">
              <div className="verification-subheading">
                <span>▦</span>
                <h3>Cylinder test records</h3>
              </div>

              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Cylinder</th>
                      <th>Last Test</th>
                      <th>Next Due</th>
                      <th>Days Left</th>
                      <th>Result</th>
                      <th>Status</th>
                    </tr>
                  </thead>

                  <tbody>
                    {cylinders.map((cylinder, index) => (
                      <tr
                        key={
                          cylinder.cylinderSerial ||
                          `${cylinder.lastTestDate}-${index}`
                        }
                      >
                        <td>{cylinder.cylinderSerial || "-"}</td>
                        <td>
                          {cylinder.lastTestDate
                            ? formatDate(cylinder.lastTestDate)
                            : "-"}
                        </td>
                        <td>
                          {cylinder.nextDueDate
                            ? formatDate(cylinder.nextDueDate)
                            : "-"}
                        </td>
                        <td>{cylinder.daysToDue ?? "-"}</td>
                        <td>{cylinder.result || "-"}</td>
                        <td>
                          <StatusBadge status={cylinder.status} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {!vehicle && cylinders.length === 0 && (
            <div className="scanner-tip">
              <span className="tip-icon">ⓘ</span>
              <div>
                <strong>Additional details unavailable</strong>
                <p>
                  The verification service did not return vehicle or
                  cylinder details for this result.
                </p>
              </div>
            </div>
          )}
        </section>
      )}
    </main>
  );
}

export default CngVerify;