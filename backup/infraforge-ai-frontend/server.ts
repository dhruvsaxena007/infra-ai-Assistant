import express from "express";
import path from "path";
import { createServer as createViteServer } from "vite";
import dotenv from "dotenv";

dotenv.config();

// ---------------------------------------------------------------------------
// Minimal dev/prod server for the Infra AI-Assistant for Marketplace frontend.
//
// The assistant talks DIRECTLY to the FastAPI backend (VITE_API_BASE_URL,
// default http://127.0.0.1:8000), which already enables CORS for this origin.
// This server therefore only serves the React app — it contains no mock data
// and no AI logic of its own.
// ---------------------------------------------------------------------------

async function startServer() {
  const app = express();
  const PORT = Number(process.env.PORT) || 3000;

  if (process.env.NODE_ENV !== "production") {
    const vite = await createViteServer({
      server: { middlewareMode: true },
      appType: "spa",
    });
    app.use(vite.middlewares);
  } else {
    const distPath = path.join(process.cwd(), "dist");
    app.use(express.static(distPath));
    app.get("*", (_req, res) => {
      res.sendFile(path.join(distPath, "index.html"));
    });
  }

  app.listen(PORT, "0.0.0.0", () => {
    console.log(`Infra AI-Assistant for Marketplace running on http://localhost:${PORT}`);
  });
}

startServer().catch((err) => {
  console.error("Server failed to start:", err);
});
