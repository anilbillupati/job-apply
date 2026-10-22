import { Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { ExtractPage } from "./pages/ExtractPage";
import { JobDetailPage } from "./pages/JobDetailPage";
import { JobsPage } from "./pages/JobsPage";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<JobsPage />} />
        <Route path="extract" element={<ExtractPage />} />
        <Route path="jobs/:id" element={<JobDetailPage />} />
        <Route path="*" element={<p>Page not found.</p>} />
      </Route>
    </Routes>
  );
}
