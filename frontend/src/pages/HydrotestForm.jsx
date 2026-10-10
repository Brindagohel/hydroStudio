import { useEffect, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { createRecord, getAssets, getRecord, updateRecord } from "../services/api.js";
import { getErrorMessage } from "../utils/format.js";
import Message from "../components/Message.jsx";
import Loading from "../components/Loading.jsx";

// Used for both "Add Hydrotest" and "Edit" (when a recordId is in the URL).
function HydrotestForm() {
  const { recordId } = useParams();
  const [searchParams] = useSearchParams();
  const isEdit = Boolean(recordId);
  const navigate = useNavigate();

  const [form, setForm] = useState({
    assetId: searchParams.get("assetId") || "",
    testDate: "",
    performedBy: "",
    result: "Pass",
    notes: "",
    reportFile: "",
    nextDueDate: "",
  });
  const [assetIds, setAssetIds] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const requests = [getAssets({ sort_by: "assetId" }).then((list) => setAssetIds(list.map((a) => a.assetId)))];
    if (isEdit) {
      requests.push(
        getRecord(recordId).then((record) =>
          setForm({
            assetId: record.assetId,
            testDate: record.testDate,
            performedBy: record.performedBy,
            result: record.result,
            notes: record.notes || "",
            reportFile: record.reportFile || "",
            nextDueDate: record.nextDueDate || "",
          })
        )
      );
    }
    Promise.all(requests)
      .catch((err) => setError(getErrorMessage(err)))
      .finally(() => setLoading(false));
  }, [recordId, isEdit]);

  const change = (event) => setForm({ ...form, [event.target.name]: event.target.value });

  const submit = async (event) => {
    event.preventDefault();
    setError("");

    if (form.nextDueDate && form.nextDueDate < form.testDate) {
      setError("Next due date cannot be earlier than the test date.");
      return;
    }
    if (form.result === "Fail" && !window.confirm("A failed test marks this asset as FAILED on the dashboard. Save it?")) {
      return;
    }

    setSaving(true);
    try {
      const body = {
        testDate: form.testDate,
        performedBy: form.performedBy,
        result: form.result,
        notes: form.notes,
        reportFile: form.reportFile || null,
        nextDueDate: form.nextDueDate || null,
      };
      if (isEdit) {
        await updateRecord(recordId, body);
      } else {
        await createRecord({ ...body, assetId: form.assetId });
      }
      navigate(`/assets/${form.assetId.trim().toUpperCase()}`);
    } catch (err) {
      setError(getErrorMessage(err));
      setSaving(false);
    }
  };

  if (loading) return <Loading />;

  return (
    <div>
      <h1>{isEdit ? "Edit Hydrotest" : "Add Hydrotest"}</h1>
      <Message type="error">{error}</Message>

      <form className="form panel" onSubmit={submit}>
        <label>
          Asset *
          <input name="assetId" value={form.assetId} onChange={change} required list="asset-ids" disabled={isEdit} />
          <datalist id="asset-ids">{assetIds.map((id) => <option key={id} value={id} />)}</datalist>
        </label>
        <label>
          Test Date *
          <input type="date" name="testDate" value={form.testDate} onChange={change} required />
        </label>
        <label>
          Performed By / Provider *
          <input name="performedBy" value={form.performedBy} onChange={change} required maxLength={100} />
        </label>
        <label>
          Result *
          <select name="result" value={form.result} onChange={change}>
            <option>Pass</option>
            <option>Fail</option>
            <option>Pending</option>
          </select>
        </label>
        <label>
          Next Due Date
          <input type="date" name="nextDueDate" value={form.nextDueDate} onChange={change} min={form.testDate || undefined} />
        </label>
        <label>
          Report file name
          <input name="reportFile" value={form.reportFile} onChange={change} placeholder="demo-report-001.pdf" maxLength={100} />
        </label>
        <label>
          Notes
          <textarea name="notes" value={form.notes} onChange={change} rows={3} maxLength={1000} />
        </label>
        <p className="hint">If a passed test has no next due date, one year after the test date is used.</p>
        <div className="button-row">
          <button className="button" type="submit" disabled={saving}>{saving ? "Saving..." : "Save Hydrotest"}</button>
          <Link className="button secondary" to={form.assetId ? `/assets/${form.assetId}` : "/hydrotests"}>Cancel</Link>
        </div>
      </form>
    </div>
  );
}

export default HydrotestForm;
