import { STATUS_LABELS } from "../utils/format.js";

function StatusBadge({ status }) {
  if (!status) return <span>-</span>;
  const label = STATUS_LABELS[status] || status;
  return <span className={`badge badge-${status.toLowerCase().replace(/_/g, "-")}`}>{label}</span>;
}

export default StatusBadge;
