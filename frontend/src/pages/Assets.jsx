import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { getAssetOptions, getAssets } from "../services/api.js";
import { formatDate, getErrorMessage, STATUS_LABELS } from "../utils/format.js";
import StatusBadge from "../components/StatusBadge.jsx";
import Message from "../components/Message.jsx";
import Loading from "../components/Loading.jsx";
import EmptyState from "../components/EmptyState.jsx";

const EMPTY_FILTERS = { search: "", station: "", asset_type: "", status: "", due_from: "", due_to: "", sort_order: "asc" };

function Assets() {
  // the dashboard cards link here with ?status=...
  const [searchParams] = useSearchParams();
  const [filters, setFilters] = useState({ ...EMPTY_FILTERS, status: searchParams.get("status") || "" });
  const [options, setOptions] = useState({ stations: [], assetTypes: [] });
  const [assets, setAssets] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    getAssetOptions().then(setOptions).catch(() => {});
  }, []);

  useEffect(() => {
    // wait a moment while the user is typing in the search box
    const timer = setTimeout(() => {
      const params = { sort_by: "nextDueDate" };
      Object.entries(filters).forEach(([key, value]) => {
        if (value) params[key] = value;
      });
      setLoading(true);
      getAssets(params)
        .then((data) => {
          setAssets(data);
          setError("");
        })
        .catch((err) => setError(getErrorMessage(err)))
        .finally(() => setLoading(false));
    }, 300);
    return () => clearTimeout(timer);
  }, [filters]);

  const change = (event) => setFilters({ ...filters, [event.target.name]: event.target.value });

  return (
    <div>
      <div className="page-header">
        <h1>Assets</h1>
        <Link className="button" to="/assets/new">Add Asset</Link>
      </div>

      <div className="filters">
        <input name="search" value={filters.search} onChange={change} placeholder="Search ID, serial, station..." />
        <select name="station" value={filters.station} onChange={change}>
          <option value="">All stations</option>
          {options.stations.map((s) => <option key={s}>{s}</option>)}
        </select>
        <select name="asset_type" value={filters.asset_type} onChange={change}>
          <option value="">All asset types</option>
          {options.assetTypes.map((t) => <option key={t}>{t}</option>)}
        </select>
        <select name="status" value={filters.status} onChange={change}>
          <option value="">All statuses</option>
          {Object.entries(STATUS_LABELS).filter(([key]) => key !== "NOT_FOUND").map(([key, label]) => (
            <option key={key} value={key}>{label}</option>
          ))}
        </select>
        <label>Due from <input type="date" name="due_from" value={filters.due_from} onChange={change} /></label>
        <label>Due to <input type="date" name="due_to" value={filters.due_to} onChange={change} /></label>
        <select name="sort_order" value={filters.sort_order} onChange={change}>
          <option value="asc">Next due: earliest first</option>
          <option value="desc">Next due: latest first</option>
        </select>
        <button type="button" className="button secondary" onClick={() => setFilters(EMPTY_FILTERS)}>Clear</button>
      </div>

      <Message type="error">{error}</Message>
      {loading && <Loading />}

      {!loading && !error && assets.length === 0 && (
        <EmptyState>No assets match these filters.</EmptyState>
      )}

      {assets.length > 0 && (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Asset ID</th>
                <th>Station</th>
                <th>Asset Type</th>
                <th>Serial Number</th>
                <th>Test Date</th>
                <th>Next Due</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {assets.map((asset) => (
                <tr key={asset.id}>
                  <td>{asset.assetId}</td>
                  <td>{asset.station}</td>
                  <td>{asset.assetType}</td>
                  <td>{asset.serialNumber}</td>
                  <td>{formatDate(asset.testDate)}</td>
                  <td>{formatDate(asset.nextDueDate)}</td>
                  <td><StatusBadge status={asset.status} /></td>
                  <td className="actions">
                    <Link to={`/assets/${asset.assetId}`}>View</Link>
                    <Link to={`/assets/${asset.assetId}/edit`}>Edit</Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export default Assets;
