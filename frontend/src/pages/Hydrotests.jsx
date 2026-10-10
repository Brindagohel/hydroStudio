import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getRecords } from "../services/api.js";
import { formatDate, getErrorMessage } from "../utils/format.js";
import Message from "../components/Message.jsx";
import Loading from "../components/Loading.jsx";
import EmptyState from "../components/EmptyState.jsx";

function Hydrotests() {
  const [records, setRecords] = useState([]);
  const [result, setResult] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    setLoading(true);
    getRecords(result ? { result } : {})
      .then((data) => {
        setRecords(data);
        setError("");
      })
      .catch((err) => setError(getErrorMessage(err)))
      .finally(() => setLoading(false));
  }, [result]);

  return (
    <div>
      <div className="page-header">
        <h1>Hydrotests</h1>
        <Link className="button" to="/hydrotests/new">Add Hydrotest</Link>
      </div>

      <div className="filters">
        <select value={result} onChange={(e) => setResult(e.target.value)}>
          <option value="">All results</option>
          <option>Pass</option>
          <option>Fail</option>
          <option>Pending</option>
        </select>
      </div>

      <Message type="error">{error}</Message>
      {loading && <Loading />}
      {!loading && !error && records.length === 0 && <EmptyState>No hydrotest records found.</EmptyState>}

      {records.length > 0 && (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Asset</th>
                <th>Test Date</th>
                <th>Provider</th>
                <th>Result</th>
                <th>Notes</th>
                <th>Report</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {records.map((record) => (
                <tr key={record.id}>
                  <td><Link to={`/assets/${record.assetId}`}>{record.assetId}</Link></td>
                  <td>{formatDate(record.testDate)}</td>
                  <td>{record.performedBy}</td>
                  <td>{record.result}</td>
                  <td>{record.notes || "-"}</td>
                  <td>{record.reportFile || "-"}</td>
                  <td><Link to={`/hydrotests/${record.id}/edit`}>Edit</Link></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export default Hydrotests;
