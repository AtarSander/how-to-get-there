import { createTheme } from "@mui/material/styles";

export const theme = createTheme({
  palette: {
    mode: "dark",
    primary: {
      main: "#5b9cf5",
    },
    secondary: {
      main: "#e8a04a",
    },
    background: {
      default: "#0b0f14",
      paper: "#121822",
    },
  },
  typography: {
    fontFamily: '"DM Sans", "Roboto", "Helvetica", "Arial", sans-serif',
    h1: {
      fontWeight: 700,
      letterSpacing: "-0.03em",
    },
  },
  shape: {
    borderRadius: 12,
  },
  components: {
    MuiCssBaseline: {
      styleOverrides: {
        body: {
          backgroundImage:
            "radial-gradient(ellipse 80% 50% at 10% -10%, rgba(56, 120, 190, 0.18), transparent), radial-gradient(ellipse 60% 40% at 90% 0%, rgba(180, 90, 40, 0.12), transparent)",
          backgroundAttachment: "fixed",
        },
      },
    },
  },
});
