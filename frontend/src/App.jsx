
import { NavLink, Route, Routes } from "react-router-dom";

import Dashboard from "./pages/Dashboard.jsx";
import Assets from "./pages/Assets.jsx";
import AssetDetails from "./pages/AssetDetails.jsx";
import AssetForm from "./pages/AssetForm.jsx";
import Hydrotests from "./pages/Hydrotests.jsx";
import HydrotestForm from "./pages/HydrotestForm.jsx";
import Inspection from "./pages/Inspection.jsx";
import CngVerify from "./pages/CngVerify.jsx";

const navItems = [
  { to: "/", label: "Dashboard", icon: "◫", end: true },
  { to: "/assets", label: "Vehicles", icon: "▤" },
  { to: "/hydrotests", label: "Hydrotests", icon: "◉" },
  { to: "/inspection", label: "AI Inspection", icon: "⌕" },
  { to: "/cng", label: "CNG Verify", icon: "✳" },
];

function App() {
  return (
    <>
      <header className="topbar">
        <div className="topbar-inner">
          <NavLink to="/" end className="brand">
            <span className="brand-mark" aria-hidden="true">
              ✳
            </span>

            <span>Hydrotest Studio</span>
          </NavLink>

          <nav aria-label="Main navigation">
            {navItems.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                title={item.label}
              >
                <span className="nav-icon" aria-hidden="true">
                  {item.icon}
                </span>
                <span>{item.label}</span>
              </NavLink>
            ))}
          </nav>
        </div>
      </header>

      <main className="container">
        <p className="demo-note">
          Verification workspace · Demo data is fictional
        </p>

        <Routes>
          <Route path="/" element={<Dashboard />} />

          <Route path="/assets" element={<Assets />} />
          <Route path="/assets/new" element={<AssetForm />} />
          <Route path="/assets/:assetId" element={<AssetDetails />} />
          <Route path="/assets/:assetId/edit" element={<AssetForm />} />

          <Route path="/hydrotests" element={<Hydrotests />} />
          <Route path="/hydrotests/new" element={<HydrotestForm />} />
          <Route
            path="/hydrotests/:recordId/edit"
            element={<HydrotestForm />}
          />

          <Route path="/inspection" element={<Inspection />} />
          <Route path="/cng" element={<CngVerify />} />

          <Route path="*" element={<p>Page not found.</p>} />
        </Routes>
      </main>
    </>
  );
}

export default App;