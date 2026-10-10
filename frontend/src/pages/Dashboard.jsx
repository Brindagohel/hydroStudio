
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { getSummary } from "../services/api.js";
import { formatDate, getErrorMessage } from "../utils/format.js";

import StatusBadge from "../components/StatusBadge.jsx";
import Message from "../components/Message.jsx";
import Loading from "../components/Loading.jsx";
import EmptyState from "../components/EmptyState.jsx";

function Dashboard() {
  const [summary, setSummary] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    getSummary()
      .then(setSummary)
      .catch((err) => setError(getErrorMessage(err)));
  }, []);

  if (error) {
    return <Message type="error">{error}</Message>;
  }

  if (!summary) {
    return <Loading text="Preparing your dashboard..." />;
  }

  const cards = [
    {
      label: "Total Vehicles",
      value: summary.totalAssets,
      className: "",
      icon: "▤",
      description: "Registered assets",
    },
    {
      label: "Valid Tests",
      value: summary.valid,
      className: "card-valid",
      status: "VALID",
      icon: "✓",
      description: "Testing up to date",
    },
    {
      label: "Due Within 30 Days",
      value: summary.dueSoon,
      className: "card-due-soon",
      status: "DUE_SOON",
      icon: "◷",
      description: "Upcoming renewals",
    },
    {
      label: "Overdue",
      value: summary.overdue,
      className: "card-overdue",
      status: "OVERDUE",
      icon: "!",
      description: "Require attention",
    },
    {
      label: "Failed",
      value: summary.failed,
      className: "card-failed",
      status: "FAILED",
      icon: "×",
      description: "Failed verification",
    },
    {
      label: "Pending",
      value: summary.pending,
      className: "card-pending",
      status: "PENDING",
      icon: "◌",
      description: "Awaiting completion",
    },
  ];

  return (
    <div className="dashboard">
      <section className="dashboard-hero">
        <div className="hero-copy">
          <span className="eyebrow">
            <span className="eyebrow-dot" />
            VEHICLE COMPLIANCE WORKSPACE
          </span>

          <h1>
            Your fleet,
            <br />
            <span>under control.</span>
          </h1>

          <p className="hero-description">
            Monitor hydrotest records, track upcoming renewals and
            verify vehicle details from one workspace.
          </p>

          <div className="hero-actions">
            <Link to="/cng" className="button">
              <span aria-hidden="true">✳</span>
              Verify a vehicle
            </Link>

            <Link to="/assets" className="button secondary">
              View vehicles <span aria-hidden="true">↗</span>
            </Link>
          </div>
        </div>

        <div className="hero-art" aria-hidden="true">
          <div className="art-orbit orbit-one" />
          <div className="art-orbit orbit-two" />

          <div className="art-circle">
            <div className="art-inner">
              <span className="art-symbol">✳</span>
              <span className="art-caption">CHECK. VERIFY. DRIVE.</span>
            </div>
          </div>

          <div className="floating-chip chip-top">
            <span className="chip-icon">✓</span>
            <span>
              <strong>Smart checks</strong>
              <small>Vehicle verification</small>
            </span>
          </div>

          <div className="floating-chip chip-bottom">
            <span className="chip-icon lilac-icon">◷</span>
            <span>
              <strong>Stay prepared</strong>
              <small>Track due dates</small>
            </span>
          </div>

          <span className="art-star star-one">✳</span>
          <span className="art-star star-two">✦</span>
        </div>
      </section>

      <section className="section-block">
        <div className="section-heading">
          <div>
            <span className="section-kicker">AT A GLANCE</span>
            <h2>Fleet overview</h2>
            <p>Your vehicle compliance summary.</p>
          </div>

          <Link to="/assets" className="text-link">
            All vehicles <span aria-hidden="true">↗</span>
          </Link>
        </div>

        <div className="cards">
          {cards.map((card, index) => (
            <Link
              key={card.label}
              to={
                card.status
                  ? `/assets?status=${card.status}`
                  : "/assets"
              }
              className={`card ${card.className}`}
              style={{ "--card-index": index }}
            >
              <div className="stat-top">
                <span className="stat-label">{card.label}</span>
                <span className="stat-icon" aria-hidden="true">
                  {card.icon}
                </span>
              </div>

              <span className="card-value">{card.value}</span>

              <span className="card-label">{card.description}</span>

              <span className="stat-link" aria-hidden="true">
                View records ↗
              </span>
            </Link>
          ))}
        </div>
      </section>

      <section className="panel dashboard-panel">
        <div className="section-heading panel-heading">
          <div>
            <span className="section-kicker">PRIORITY QUEUE</span>
            <h2>Needs attention</h2>
            <p>Vehicles with upcoming or overdue testing.</p>
          </div>

          <span className="count-pill">
            {summary.needsAttention.length} records
          </span>
        </div>

        {summary.needsAttention.length === 0 ? (
          <EmptyState>
            No assets are due, overdue or failed right now.
          </EmptyState>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Vehicle ID</th>
                  <th>Station</th>
                  <th>Vehicle type</th>
                  <th>Next due</th>
                  <th>Status</th>
                </tr>
              </thead>

              <tbody>
                {summary.needsAttention.map((asset) => (
                  <tr key={asset.id}>
                    <td>
                      <Link
                        className="table-link"
                        to={`/assets/${asset.assetId}`}
                      >
                        {asset.assetId}
                      </Link>
                    </td>

                    <td>{asset.station}</td>
                    <td>{asset.assetType}</td>
                    <td>{formatDate(asset.nextDueDate)}</td>
                    <td>
                      <StatusBadge status={asset.status} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="panel dashboard-panel">
        <div className="section-heading panel-heading">
          <div>
            <span className="section-kicker">ACTIVITY</span>
            <h2>Recent hydrotests</h2>
            <p>A quick look at recently recorded tests.</p>
          </div>

          <Link to="/hydrotests" className="text-link">
            All records <span aria-hidden="true">↗</span>
          </Link>
        </div>

        {summary.recentRecords.length === 0 ? (
          <EmptyState>No hydrotest records yet.</EmptyState>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Vehicle ID</th>
                  <th>Test date</th>
                  <th>Testing provider</th>
                  <th>Result</th>
                </tr>
              </thead>

              <tbody>
                {summary.recentRecords.map((record) => (
                  <tr key={record.id}>
                    <td>
                      <Link
                        className="table-link"
                        to={`/assets/${record.assetId}`}
                      >
                        {record.assetId}
                      </Link>
                    </td>

                    <td>{formatDate(record.testDate)}</td>
                    <td>{record.performedBy}</td>
                    <td>{record.result}</td>
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

export default Dashboard;