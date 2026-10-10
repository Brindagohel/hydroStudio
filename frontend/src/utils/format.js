// Dates come from the API as "YYYY-MM-DD" and are shown as DD-MM-YYYY.
export function formatDate(value) {
  if (!value) return "-";
  const [year, month, day] = value.split("T")[0].split("-");
  return `${day}-${month}-${year}`;
}

export const STATUS_LABELS = {
  VALID: "Valid",
  DUE_SOON: "Due soon",
  OVERDUE: "Overdue",
  FAILED: "Failed",
  PENDING: "Pending",
  NOT_FOUND: "Not found",
  EXPIRED: "Expired",
  NO_RECORD: "No test record",
  NOT_CNG: "Not a CNG vehicle",
  VEHICLE_NOT_FOUND: "Vehicle not found",
};

export function getErrorMessage(error) {
  if (error.response) {
    const detail = error.response.data && error.response.data.detail;
    if (typeof detail === "string") return detail;
    return `The server returned an error (${error.response.status}).`;
  }
  if (error.code === "ECONNABORTED") return "The request took too long. Please try again.";
  return "Could not reach the server. Check that the backend is running.";
}
