import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { Toaster } from "sonner";
import { Layout } from "@/components/Layout";
import { NewSearch } from "@/pages/NewSearch";
import { Results } from "@/pages/Results";
import { RunProgress } from "@/pages/RunProgress";
import { Runs } from "@/pages/Runs";
import { Settings } from "@/pages/Settings";
import "./index.css";

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false, staleTime: 5_000 } },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<Navigate to="/runs" replace />} />
            <Route path="new" element={<NewSearch />} />
            <Route path="runs" element={<Runs />} />
            <Route path="runs/:id" element={<RunProgress />} />
            <Route path="runs/:id/results" element={<Results />} />
            <Route path="settings" element={<Settings />} />
            <Route path="*" element={<Navigate to="/runs" replace />} />
          </Route>
        </Routes>
      </BrowserRouter>
      <Toaster richColors theme="system" position="bottom-right" />
    </QueryClientProvider>
  </StrictMode>,
);
