import { useMemo, useState } from "react";
import DirectionsCarIcon from "@mui/icons-material/DirectionsCar";
import DirectionsTransitIcon from "@mui/icons-material/DirectionsTransit";
import LocalParkingIcon from "@mui/icons-material/LocalParking";
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Container,
  Divider,
  Grid,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import { compareRoutes } from "./api";

const WARSAW_PRESETS = {
  centrum: { lat: 52.2297, lon: 21.0122, label: "Centrum" },
  wola: { lat: 52.2309, lon: 20.9862, label: "Wola" },
  praga: { lat: 52.2551, lon: 21.0354, label: "Praga Północ" },
  mokotow: { lat: 52.1934, lon: 21.0346, label: "Mokotów" },
};

const MODE_ICONS = {
  car: DirectionsCarIcon,
  public_transport: DirectionsTransitIcon,
  park_and_ride: LocalParkingIcon,
};

const MODE_COLORS = {
  car: "warning",
  public_transport: "success",
  park_and_ride: "primary",
};

function formatTime(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleTimeString("pl-PL", {
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatDistance(meters) {
  if (meters === null || meters === undefined) return "—";
  if (meters >= 1000) return `${(meters / 1000).toFixed(1)} km`;
  return `${Math.round(meters)} m`;
}

function getPublicTransportLegs(option) {
  const details = option.details?.public_transport;
  return details?.legs ?? null;
}

function OptionCard({ option, highlighted }) {
  const Icon = MODE_ICONS[option.mode] ?? DirectionsTransitIcon;
  const color = MODE_COLORS[option.mode] ?? "default";
  const legs = getPublicTransportLegs(option);

  return (
    <Card
      variant="outlined"
      sx={{
        borderLeftWidth: 4,
        borderLeftStyle: "solid",
        borderLeftColor: `${color}.main`,
        opacity: option.available ? 1 : 0.7,
        outline: highlighted ? (theme) => `1px solid ${theme.palette.primary.main}` : "none",
      }}
    >
      <CardContent>
        <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1.5 }}>
          <Icon color={color} fontSize="small" />
          <Typography variant="subtitle1" fontWeight={600}>
            {option.label}
          </Typography>
          {highlighted && (
            <Chip label="Najszybsza" size="small" color="primary" variant="outlined" />
          )}
        </Stack>

        {option.available ? (
          <>
            <Grid container spacing={2}>
              <Grid size={{ xs: 6, sm: 4 }}>
                <Typography variant="caption" color="text.secondary" display="block">
                  Czas
                </Typography>
                <Typography fontWeight={600}>{option.total_minutes} min</Typography>
              </Grid>
              <Grid size={{ xs: 6, sm: 4 }}>
                <Typography variant="caption" color="text.secondary" display="block">
                  Odjazd
                </Typography>
                <Typography fontWeight={600}>{formatTime(option.departure_at)}</Typography>
              </Grid>
              <Grid size={{ xs: 6, sm: 4 }}>
                <Typography variant="caption" color="text.secondary" display="block">
                  Przyjazd
                </Typography>
                <Typography fontWeight={600}>{formatTime(option.arrival_at)}</Typography>
              </Grid>
              <Grid size={{ xs: 6, sm: 4 }}>
                <Typography variant="caption" color="text.secondary" display="block">
                  Dystans
                </Typography>
                <Typography fontWeight={600}>
                  {formatDistance(option.total_distance_m)}
                </Typography>
              </Grid>
              <Grid size={{ xs: 6, sm: 4 }}>
                <Typography variant="caption" color="text.secondary" display="block">
                  Przesiadki
                </Typography>
                <Typography fontWeight={600}>{option.transfers ?? 0}</Typography>
              </Grid>
            </Grid>

            {legs && legs.length > 0 && (
              <Box component="ol" sx={{ mt: 2, mb: 0, pl: 2.5, color: "text.secondary" }}>
                {legs.map((leg, index) => (
                  <Typography component="li" variant="body2" key={`${leg.from_name}-${index}`}>
                    {leg.from_name} → {leg.to_name}
                    {leg.route_name ? ` (${leg.route_name})` : ""}
                  </Typography>
                ))}
              </Box>
            )}
          </>
        ) : (
          <Typography variant="body2" color="text.secondary">
            {option.reason}
          </Typography>
        )}
      </CardContent>
    </Card>
  );
}

function PresetChips({ target, onSelect }) {
  return (
    <Stack direction="row" flexWrap="wrap" gap={0.75} sx={{ mt: 1 }}>
      {Object.entries(WARSAW_PRESETS).map(([key, preset]) => (
        <Chip
          key={`${target}-${key}`}
          label={preset.label}
          size="small"
          variant="outlined"
          onClick={() => onSelect(key, target)}
        />
      ))}
    </Stack>
  );
}

export default function App() {
  const [originLat, setOriginLat] = useState(String(WARSAW_PRESETS.centrum.lat));
  const [originLon, setOriginLon] = useState(String(WARSAW_PRESETS.centrum.lon));
  const [destinationLat, setDestinationLat] = useState(String(WARSAW_PRESETS.mokotow.lat));
  const [destinationLon, setDestinationLon] = useState(String(WARSAW_PRESETS.mokotow.lon));
  const [departureAt, setDepartureAt] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);

  const departureDefault = useMemo(() => {
    const now = new Date();
    now.setSeconds(0, 0);
    const offset = now.getTimezoneOffset();
    const local = new Date(now.getTime() - offset * 60_000);
    return local.toISOString().slice(0, 16);
  }, []);

  async function handleSubmit(event) {
    event.preventDefault();
    setLoading(true);
    setError(null);

    try {
      const comparison = await compareRoutes({
        origin_lat: Number(originLat),
        origin_lon: Number(originLon),
        destination_lat: Number(destinationLat),
        destination_lon: Number(destinationLon),
        departure_at: departureAt || undefined,
      });
      setResult(comparison);
    } catch (submitError) {
      setResult(null);
      setError(
        submitError instanceof Error ? submitError.message : "Unknown error.",
      );
    } finally {
      setLoading(false);
    }
  }

  function applyPreset(presetKey, target) {
    const point = WARSAW_PRESETS[presetKey];
    if (target === "origin") {
      setOriginLat(String(point.lat));
      setOriginLon(String(point.lon));
    } else {
      setDestinationLat(String(point.lat));
      setDestinationLon(String(point.lon));
    }
  }

  return (
    <Container maxWidth="lg" sx={{ py: { xs: 3, md: 5 } }}>
      <Box sx={{ mb: 4 }}>
        <Typography
          variant="overline"
          color="text.secondary"
          sx={{ fontFamily: '"IBM Plex Mono", monospace', letterSpacing: "0.12em" }}
        >
          Warszawa · SPDB
        </Typography>
        <Typography variant="h3" component="h1" sx={{ mt: 0.5 }}>
          Jak tam dojechać?
        </Typography>
        <Typography variant="body1" color="text.secondary" sx={{ mt: 1, maxWidth: 560 }}>
          Porównanie samochodu, komunikacji miejskiej i Park &amp; Ride na danych GTFS
          i OSM.
        </Typography>
      </Box>

      <Grid container spacing={2.5}>
        <Grid size={{ xs: 12, md: 4 }}>
          <Card component="form" onSubmit={handleSubmit} variant="outlined">
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Trasa
              </Typography>

              <Typography variant="subtitle2" color="text.secondary" sx={{ mt: 2, mb: 1 }}>
                Start
              </Typography>
              <Grid container spacing={1.5}>
                <Grid size={6}>
                  <TextField
                    label="Szerokość"
                    type="number"
                    value={originLat}
                    onChange={(e) => setOriginLat(e.target.value)}
                    required
                    fullWidth
                    size="small"
                    inputProps={{ step: "any" }}
                  />
                </Grid>
                <Grid size={6}>
                  <TextField
                    label="Długość"
                    type="number"
                    value={originLon}
                    onChange={(e) => setOriginLon(e.target.value)}
                    required
                    fullWidth
                    size="small"
                    inputProps={{ step: "any" }}
                  />
                </Grid>
              </Grid>
              <PresetChips target="origin" onSelect={applyPreset} />

              <Divider sx={{ my: 2.5 }} />

              <Typography variant="subtitle2" color="text.secondary" sx={{ mb: 1 }}>
                Cel
              </Typography>
              <Grid container spacing={1.5}>
                <Grid size={6}>
                  <TextField
                    label="Szerokość"
                    type="number"
                    value={destinationLat}
                    onChange={(e) => setDestinationLat(e.target.value)}
                    required
                    fullWidth
                    size="small"
                    inputProps={{ step: "any" }}
                  />
                </Grid>
                <Grid size={6}>
                  <TextField
                    label="Długość"
                    type="number"
                    value={destinationLon}
                    onChange={(e) => setDestinationLon(e.target.value)}
                    required
                    fullWidth
                    size="small"
                    inputProps={{ step: "any" }}
                  />
                </Grid>
              </Grid>
              <PresetChips target="destination" onSelect={applyPreset} />

              <TextField
                label="Wyjazd (opcjonalnie)"
                type="datetime-local"
                value={departureAt}
                onChange={(e) => setDepartureAt(e.target.value)}
                fullWidth
                size="small"
                sx={{ mt: 2.5 }}
                slotProps={{
                  inputLabel: { shrink: true },
                  htmlInput: { placeholder: departureDefault },
                }}
              />

              <Button
                type="submit"
                variant="contained"
                fullWidth
                size="large"
                disabled={loading}
                sx={{ mt: 2.5 }}
              >
                {loading ? (
                  <Stack direction="row" spacing={1} alignItems="center">
                    <CircularProgress size={20} color="inherit" />
                    <span>Szukam tras…</span>
                  </Stack>
                ) : (
                  "Porównaj opcje"
                )}
              </Button>

              {error && (
                <Alert severity="error" sx={{ mt: 2 }}>
                  {error}
                </Alert>
              )}
            </CardContent>
          </Card>
        </Grid>

        <Grid size={{ xs: 12, md: 8 }}>
          <Typography variant="h6" gutterBottom>
            Wyniki
          </Typography>

          {!result && !loading && (
            <Typography color="text.secondary">
              Ustaw punkty startu i celu, potem uruchom porównanie.
            </Typography>
          )}

          {result && (
            <Stack spacing={1.5}>
              {result.options.map((option) => (
                <OptionCard
                  key={option.mode}
                  option={option}
                  highlighted={result.best_option?.mode === option.mode}
                />
              ))}
            </Stack>
          )}
        </Grid>
      </Grid>
    </Container>
  );
}
