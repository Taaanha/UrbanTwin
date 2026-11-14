import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import Layout from "./layout";
import Accountability from "./pages/Accountability";
import Admin from "./pages/Admin";
import CitizenReport from "./pages/CitizenReport";
import Dashboard from "./pages/Dashboard";
import Intelligence from "./pages/Intelligence";
import Investigator from "./pages/Investigator";
import Observatory from "./pages/Observatory";
import Overview from "./pages/Overview";
import Planner from "./pages/Planner";
import Simulation from "./pages/Simulation";
import TrackReport from "./pages/TrackReport";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<CitizenReport />} />
          <Route path="/track" element={<TrackReport />} />
          <Route path="/track/:trackingId" element={<TrackReport />} />
          <Route path="/overview" element={<Overview />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/investigator" element={<Investigator />} />
          <Route path="/investigator/:trackingId" element={<Investigator />} />
          <Route path="/intelligence" element={<Intelligence />} />
          <Route path="/intelligence/:publicId" element={<Intelligence />} />
          <Route path="/planner" element={<Planner />} />
          <Route path="/accountability" element={<Accountability />} />
          <Route path="/accountability/:publicId" element={<Accountability />} />
          <Route path="/observatory" element={<Observatory />} />
          <Route path="/simulation" element={<Simulation />} />
          <Route path="/admin" element={<Admin />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
