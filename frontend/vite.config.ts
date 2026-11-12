import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The API base defaults to the local FastAPI server (CORS is configured for :5173).
// Override with VITE_API_BASE if the backend runs elsewhere.
export default defineConfig({
  plugins: [react()],
  server: { port: 5173 },
});
