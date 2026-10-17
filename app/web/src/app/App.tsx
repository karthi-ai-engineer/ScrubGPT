import { QueryClientProvider, type QueryClient } from "@tanstack/react-query";
import { lazy, Suspense, useState, type ReactNode } from "react";
import { I18nextProvider } from "react-i18next";
import { Route, Routes } from "react-router";

import { createQueryClient } from "@/api/hooks";
import { LoadingState } from "@/components/QueryStatus";
import i18n from "@/i18n";
import { CasePage } from "@/pages/CasePage";
import { HomePage } from "@/pages/HomePage";
import { AnswerPage } from "@/pages/answer/AnswerPage";
import { NotFoundPage } from "@/pages/NotFoundPage";

import { Layout } from "./Layout";

// The Control Room carries Cytoscape.js (J8), so it loads as its own chunk.
const ControlRoomPage = lazy(() =>
  import("@/pages/control-room/ControlRoomPage").then((m) => ({ default: m.ControlRoomPage })),
);

/** The route table. A router (`BrowserRouter`, or `MemoryRouter` in tests) wraps it. */
export function AppRoutes() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<HomePage />} />
        <Route path="cases/:caseId" element={<CasePage />} />
        <Route
          path="cases/:caseId/control-room"
          element={
            <Suspense fallback={<LoadingState />}>
              <ControlRoomPage />
            </Suspense>
          }
        />
        <Route path="cases/:caseId/answer" element={<AnswerPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}

/** Providers shared by the app and the tests. */
export function AppProviders({ children, queryClient }: { children: ReactNode; queryClient?: QueryClient }) {
  const [client] = useState(() => queryClient ?? createQueryClient());
  return (
    <I18nextProvider i18n={i18n}>
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    </I18nextProvider>
  );
}
