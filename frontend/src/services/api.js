import axios from "axios";

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || "/api",
  timeout: 60000,
});

// ---- assets ----
export const getSummary = () => api.get("/hydrotests/summary").then((r) => r.data);
export const getAssets = (params) => api.get("/hydrotests/assets", { params }).then((r) => r.data);
export const getAssetOptions = () => api.get("/hydrotests/assets/options").then((r) => r.data);
export const getAsset = (assetId) => api.get(`/hydrotests/assets/${encodeURIComponent(assetId)}`).then((r) => r.data);
export const createAsset = (data) => api.post("/hydrotests/assets", data).then((r) => r.data);
export const updateAsset = (assetId, data) =>
  api.patch(`/hydrotests/assets/${encodeURIComponent(assetId)}`, data).then((r) => r.data);

// ---- hydrotest records ----
export const getRecords = (params) => api.get("/hydrotests/records", { params }).then((r) => r.data);
export const getRecord = (id) => api.get(`/hydrotests/records/${id}`).then((r) => r.data);
export const createRecord = (data) => api.post("/hydrotests/records", data).then((r) => r.data);
export const updateRecord = (id, data) => api.patch(`/hydrotests/records/${id}`, data).then((r) => r.data);

// ---- inspection ----

export const scanFrame = (blob, save = false) => {
  const form = new FormData();
  form.append("file", blob, "frame.jpg");
  return api.post("/inspection/scan-frame", form, { params: { save }, timeout: 60000 }).then((r) => r.data);
};
// Quick "is the whole plate in view, big and sharp?" check on a small camera frame (YOLO only, no OCR).
export const detectPlate = (blob, fullWidth) => {
  const form = new FormData();
  form.append("file", blob, "preview.jpg");
  return api
    .post("/inspection/detect-plate", form, { params: fullWidth ? { full_width: fullWidth } : {}, timeout: 15000 })
    .then((r) => r.data);
};
export const uploadVideo = (file) => {
  const form = new FormData();
  form.append("file", file);
  return api.post("/inspection/upload-video", form, { timeout: 300000 }).then((r) => r.data);
};
export const processVideo = (inspectionId) =>
  api.post("/inspection/process-video", { inspectionId }).then((r) => r.data);
export const getInspection = (id) => api.get(`/inspection/results/${id}`).then((r) => r.data);
export const correctPlate = (id, plateNumber) =>
  api.patch(`/inspection/results/${id}`, { plateNumber }).then((r) => r.data);
export const plateImageUrl = (id) => `${api.defaults.baseURL}/inspection/results/${id}/plate-image`;

// ---- CNG verification (camera -> plate -> vehicle lookup -> hydrotest check) ----
export const scanImage = (blob) => {
  const form = new FormData();
  form.append("file", blob, "capture.jpg");
  return api.post("/cng/scan", form, { timeout: 60000 }).then((r) => r.data);
};
export const verifyPlate = (plate) =>
  api.get(`/cng/verify/${encodeURIComponent(plate)}`).then((r) => r.data);