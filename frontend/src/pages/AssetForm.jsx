import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { createAsset, getAsset, getAssetOptions, updateAsset } from "../services/api.js";
import { getErrorMessage } from "../utils/format.js";
import Message from "../components/Message.jsx";
import Loading from "../components/Loading.jsx";

const DEFAULT_TYPES = ["Tanker Truck", "Storage Tank", "Pressure Vessel", "Hose Assembly"];

const EMPTY = { assetId: "", station: "", assetType: "", serialNumber: "", testDate: "", nextDueDate: "" };

// Used for both "Add Asset" (no assetId in the URL) and "Edit Asset".
function AssetForm() {
  const { assetId } = useParams();
  const isEdit = Boolean(assetId);
  const navigate = useNavigate();

  const [form, setForm] = useState(EMPTY);
  const [options, setOptions] = useState({ stations: [], assetTypes: [] });
  const [loading, setLoading] = useState(isEdit);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    getAssetOptions().then(setOptions).catch(() => {});
    if (isEdit) {
      getAsset(assetId)
        .then((asset) =>
          setForm({
            assetId: asset.assetId,
            station: asset.station,
            assetType: asset.assetType,
            serialNumber: asset.serialNumber,
            testDate: asset.testDate || "",
            nextDueDate: asset.nextDueDate || "",
          })
        )
        .catch((err) => setError(getErrorMessage(err)))
        .finally(() => setLoading(false));
    }
  }, [assetId, isEdit]);

  const change = (event) => setForm({ ...form, [event.target.name]: event.target.value });

  const submit = async (event) => {
    event.preventDefault();
    setError("");

    if (form.testDate && form.nextDueDate && form.nextDueDate < form.testDate) {
      setError("Next due date cannot be earlier than the test date.");
      return;
    }

    setSaving(true);
    try {
      const body = { ...form, testDate: form.testDate || null, nextDueDate: form.nextDueDate || null };
      if (isEdit) {
        delete body.assetId; // the asset ID cannot be changed
        await updateAsset(assetId, body);
      } else {
        await createAsset(body);
      }
      navigate(`/assets/${isEdit ? assetId : form.assetId.trim().toUpperCase()}`);
    } catch (err) {
      setError(getErrorMessage(err));
      setSaving(false);
    }
  };

  if (loading) return <Loading />;

  const stationList = options.stations;
  const typeList = [...new Set([...DEFAULT_TYPES, ...options.assetTypes])];

  return (
    <div>
      <h1>{isEdit ? `Edit ${assetId}` : "Add Asset"}</h1>
      <Message type="error">{error}</Message>

      <form className="form panel" onSubmit={submit}>
        <label>
          Asset ID *
          <input name="assetId" value={form.assetId} onChange={change} required maxLength={50} disabled={isEdit} />
        </label>
        <label>
          Station / Site *
          <input name="station" value={form.station} onChange={change} required list="stations" maxLength={100} />
          <datalist id="stations">{stationList.map((s) => <option key={s} value={s} />)}</datalist>
        </label>
        <label>
          Asset Type *
          <input name="assetType" value={form.assetType} onChange={change} required list="types" maxLength={50} />
          <datalist id="types">{typeList.map((t) => <option key={t} value={t} />)}</datalist>
        </label>
        <label>
          Serial / Reference Number *
          <input name="serialNumber" value={form.serialNumber} onChange={change} required maxLength={50} />
        </label>
        <label>
          Test Date
          <input type="date" name="testDate" value={form.testDate} onChange={change} />
        </label>
        <label>
          Next Due Date
          <input type="date" name="nextDueDate" value={form.nextDueDate} onChange={change} min={form.testDate || undefined} />
        </label>
        <p className="hint">
          The status is worked out automatically from the latest hydrotest and the next due date.
        </p>
        <div className="button-row">
          <button className="button" type="submit" disabled={saving}>{saving ? "Saving..." : "Save Asset"}</button>
          <Link className="button secondary" to={isEdit ? `/assets/${assetId}` : "/assets"}>Cancel</Link>
        </div>
      </form>
    </div>
  );
}

export default AssetForm;
