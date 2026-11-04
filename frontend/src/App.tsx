import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createBrowserRouter, RouterProvider } from "react-router";
import { APP_NAME } from "@/lib/constants";

const queryClient = new QueryClient();

const router = createBrowserRouter([
  {
    path: "/",
    element: <h1 className="p-8 text-2xl font-semibold">{APP_NAME}</h1>,
  },
]);

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  );
}
