import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getAsset, getRecords } from "../services/api.js";
import { formatDate, getErrorMessage } from "../utils/format.js";
import StatusBadge from "../components/StatusBadge.jsx";
import Message from "../components/Message.jsx";
import Loading from "../components/Loading.jsx";
import EmptyState from "../components/EmptyState.jsx";

function AssetDetails() {
  const { assetId } = useParams();
  const [asset, setAsset] = useState(null);
  const [records, setRecords] = useState([]);
  const [error, setError] = useState("");

  useEffect(() => {
    setAsset(null);
    Promise.all([getAsset(assetId), getRecords({ asset_id: assetId })])
      .then(([assetData, recordData]) => {
        setAsset(assetData);
        setRecords(recordData);
      })
      .catch((err) => setError(getErrorMessage(err)));
  }, [assetId]);

  if (error) {
    return (
      <div>
        <Message type="error">{error}</Message>
        <Link to="/assets">Back to assets</Link>
      </div>
    );
  }
  if (!asset) return <Loading />;

  return (
    <div>
      <div className="page-header">
        <h1>{asset.assetId}</h1>
        <div className="button-row">
          <Link className="button secondary" to={`/assets/${asset.assetId}/edit`}>Edit Asset</Link>
          <Link className="button" to={`/hydrotests/new?assetId=${asset.assetId}`}>Add Hydrotest</Link>
        </div>
      </div>

      <section className="panel">
        <dl className="details">
          <div><dt>Status</dt><dd><StatusBadge status={asset.status} /></dd></div>
          <div><dt>Station</dt><dd>{asset.station}</dd></div>
          <div><dt>Asset Type</dt><dd>{asset.assetType}</dd></div>
          <div><dt>Serial Number</dt><dd>{asset.serialNumber}</dd></div>
          <div><dt>Last Test</dt><dd>{formatDate(asset.testDate)}</dd></div>
          <div><dt>Next Due</dt><dd>{formatDate(asset.nextDueDate)}</dd></div>
        </dl>
      </section>

      <section className="panel">
        <h2>Hydrotest history</h2>
        {records.length === 0 ? (
          <EmptyState>No hydrotests have been recorded for this asset yet.</EmptyState>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Test Date</th>
                  <th>Provider</th>
                  <th>Result</th>
                  <th>Next Due</th>
                  <th>Notes</th>
                  <th>Report</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {records.map((record) => (
                  <tr key={record.id}>
                    <td>{formatDate(record.testDate)}</td>
                    <td>{record.performedBy}</td>
                    <td>{record.result}</td>
                    <td>{formatDate(record.nextDueDate)}</td>
                    <td>{record.notes || "-"}</td>
                    <td>{record.reportFile || "-"}</td>
                    <td><Link to={`/hydrotests/${record.id}/edit`}>Edit</Link></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}

export default AssetDetails;
