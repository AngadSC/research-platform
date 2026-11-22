import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createBrowserRouter, RouterProvider } from "react-router";
import { routes } from "@/routes";
import { ApiError } from "@/lib/api";

const queryClient = new QueryClient({
  // Data stays fresh for 30 s, so revisiting a page shows it at once instead of refetching it all.
  // Mutations invalidate what they change; polled and editor queries set their own timing.
  defaultOptions: {
    queries: {
      // One retry for network blips and server errors; a 4xx answer will not change on retry.
      retry: (count, err) => count < 1 && !(err instanceof ApiError && err.status < 500),
      staleTime: 30_000,
      refetchOnWindowFocus: false,
    },
  },
});
const router = createBrowserRouter(routes);

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  );
}
