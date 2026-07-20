import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import ExtApp from "./ExtApp";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ExtApp />
  </StrictMode>
);
