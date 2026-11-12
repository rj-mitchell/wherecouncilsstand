/** Report a problem, ask for something to be taken down, or add a statement in your own words (docs/DECISIONS.md, 9
 * and 22): components/ReportForm.tsx. */
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";
import { ReportForm } from "./components/ReportForm";
import { markNav } from "./format";

markNav();
createRoot(document.getElementById("report")!).render(
  <StrictMode>
    <ReportForm search={location.search} />
  </StrictMode>,
);
