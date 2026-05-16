import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { CssBaseline, ThemeProvider } from "@mui/material";
import App from "./App";
import { LanguageProvider } from "./language/LanguageContext";
import { theme } from "./theme";

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <LanguageProvider>
      <ThemeProvider theme={theme}>
        <CssBaseline />
        <App />
      </ThemeProvider>
    </LanguageProvider>
  </StrictMode>,
);
