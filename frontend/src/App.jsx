import { useMemo, useState } from "react";
import DirectionsCarIcon from "@mui/icons-material/DirectionsCar";
import DirectionsTransitIcon from "@mui/icons-material/DirectionsTransit";
import LocalParkingIcon from "@mui/icons-material/LocalParking";
import PlaceIcon from "@mui/icons-material/Place";
import FlagIcon from "@mui/icons-material/Flag";
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
  ToggleButton,
  ToggleButtonGroup,
  Typography,
} from "@mui/material";
import AddressSearch from "./AddressSearch";
import { compareRoutes } from "./api";
import { useLanguage } from "./language/LanguageContext";
import {
  buildJourneyTimeline,
  collectDisplayLegs,
  formatLegModeLabel,
} from "./journeyDisplay";
import {
  getOptionDisplayLabel,
  getOptionReason,
  translateLegPlaceName,
} from "./language/routeLabels";
import { SUPPORTED_LOCALES } from "./language/translations";
import RouteMap from "./RouteMap";

const WARSAW_PRESET_KEYS = ["centrum", "wola", "praga", "mokotow"];

const WARSAW_PRESETS = {
  centrum: { lat: 52.2297, lon: 21.0122 },
  wola: { lat: 52.2309, lon: 20.9862 },
  praga: { lat: 52.2551, lon: 21.0354 },
  mokotow: { lat: 52.1934, lon: 21.0346 },
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

function formatTime(iso, locale) {
  if (!iso) return "—";
  const tag = locale === "en" ? "en-GB" : "pl-PL";
  return new Date(iso).toLocaleTimeString(tag, {
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatDistance(meters) {
  if (meters === null || meters === undefined) return "—";
  if (meters >= 1000) {
    return `${(meters / 1000).toFixed(1)} km`;
  }
  return `${Math.round(meters)} m`;
}

function JourneyTimeline({ option }) {
  const { locale, t } = useLanguage();
  const legs = collectDisplayLegs(option);
  if (!legs?.length) {
    return null;
  }

  const timeline = buildJourneyTimeline(legs);

  return (
    <Box component="ul" sx={{ mt: 2, mb: 0, pl: 0, listStyle: "none" }}>
      {timeline.map((item) => {
        if (item.type === "transfer") {
          return (
            <Box
              component="li"
              key={`transfer-${item.stopName}-${item.arrivalAt}`}
              sx={{
                py: 0.75,
                px: 1,
                mb: 0.75,
                borderRadius: 1,
                bgcolor: "action.hover",
                borderLeft: "3px solid",
                borderColor: "warning.main",
              }}
            >
              <Typography variant="body2" fontWeight={600} color="text.primary">
                {t("leg.transferAt", { stop: translateLegPlaceName(item.stopName, t) })}
              </Typography>
              <Typography variant="caption" color="text.secondary" display="block">
                {t("leg.transferWait", {
                  arrival: formatTime(item.arrivalAt, locale),
                  departure: formatTime(item.departureAt, locale),
                  minutes: item.waitMinutes ?? 0,
                })}
              </Typography>
            </Box>
          );
        }

        const { leg } = item;
        const modeLabel = formatLegModeLabel(leg, t);

        return (
          <Box component="li" key={`leg-${item.index}-${leg.departure_at}`} sx={{ mb: 0.75 }}>
            <Typography variant="body2" color="text.primary">
              <Box component="span" sx={{ fontFamily: '"IBM Plex Mono", monospace', mr: 1 }}>
                {formatTime(leg.departure_at, locale)}–{formatTime(leg.arrival_at, locale)}
              </Box>
              {translateLegPlaceName(leg.from_name, t)} →{" "}
              {translateLegPlaceName(leg.to_name, t)}
            </Typography>
            {modeLabel && (
              <Typography variant="caption" color="text.secondary" display="block">
                {modeLabel}
                {leg.trip_headsign ? ` · ${leg.trip_headsign}` : ""}
              </Typography>
            )}
          </Box>
        );
      })}
    </Box>
  );
}

function LanguageSwitcher() {
  const { locale, setLocale, t } = useLanguage();

  return (
    <ToggleButtonGroup
      exclusive
      size="small"
      value={locale}
      onChange={(_event, value) => value && setLocale(value)}
      aria-label="Language"
    >
      {SUPPORTED_LOCALES.map((code) => (
        <ToggleButton key={code} value={code}>
          {t(`locale.${code}`)}
        </ToggleButton>
      ))}
    </ToggleButtonGroup>
  );
}

function OptionCard({ option, highlighted, selected, onSelect }) {
  const { locale, t } = useLanguage();
  const Icon = MODE_ICONS[option.mode] ?? DirectionsTransitIcon;
  const color = MODE_COLORS[option.mode] ?? "default";
  const label = getOptionDisplayLabel(option, t);
  const reason = getOptionReason(option, t);

  return (
    <Card
      variant="outlined"
      onClick={() => option.available && onSelect(option.mode)}
      sx={{
        borderLeftWidth: 4,
        borderLeftStyle: "solid",
        borderLeftColor: `${color}.main`,
        opacity: option.available ? 1 : 0.7,
        cursor: option.available ? "pointer" : "default",
        outline: (theme) => {
          if (selected) {
            return `2px solid ${theme.palette.primary.main}`;
          }
          if (highlighted) {
            return `1px solid ${theme.palette.primary.main}`;
          }
          return "none";
        },
      }}
    >
      <CardContent>
          <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1.5 }}>
            <Icon color={color} fontSize="small" />
            <Typography variant="subtitle1" fontWeight={600}>
              {label}
            </Typography>
            {highlighted && (
              <Chip
                label={t("option.fastest")}
                size="small"
                color="primary"
                variant="outlined"
              />
            )}
          </Stack>

          {option.available ? (
            <>
              <Grid container spacing={2}>
                <Grid size={{ xs: 6, sm: 4 }}>
                  <Typography variant="caption" color="text.secondary" display="block">
                    {t("option.duration")}
                  </Typography>
                  <Typography fontWeight={600}>
                    {option.total_minutes} {t("option.minutes")}
                  </Typography>
                </Grid>
                <Grid size={{ xs: 6, sm: 4 }}>
                  <Typography variant="caption" color="text.secondary" display="block">
                    {t("option.departure")}
                  </Typography>
                  <Typography fontWeight={600}>
                    {formatTime(option.departure_at, locale)}
                  </Typography>
                </Grid>
                <Grid size={{ xs: 6, sm: 4 }}>
                  <Typography variant="caption" color="text.secondary" display="block">
                    {t("option.arrival")}
                  </Typography>
                  <Typography fontWeight={600}>
                    {formatTime(option.arrival_at, locale)}
                  </Typography>
                </Grid>
                <Grid size={{ xs: 6, sm: 4 }}>
                  <Typography variant="caption" color="text.secondary" display="block">
                    {t("option.distance")}
                  </Typography>
                  <Typography fontWeight={600}>
                    {formatDistance(option.total_distance_m)}
                  </Typography>
                </Grid>
                <Grid size={{ xs: 6, sm: 4 }}>
                  <Typography variant="caption" color="text.secondary" display="block">
                    {t("option.transfers")}
                  </Typography>
                  <Typography fontWeight={600}>{option.transfers ?? 0}</Typography>
                </Grid>
              </Grid>

              <JourneyTimeline option={option} />
            </>
          ) : (
            <Typography variant="body2" color="text.secondary">
              {reason}
            </Typography>
          )}
      </CardContent>
    </Card>
  );
}

function PresetChips({ target, onSelect }) {
  const { t } = useLanguage();

  return (
    <Stack direction="row" flexWrap="wrap" gap={0.75} sx={{ mt: 1 }}>
      {WARSAW_PRESET_KEYS.map((key) => (
        <Chip
          key={`${target}-${key}`}
          label={t(`presets.${key}`)}
          size="small"
          variant="outlined"
          onClick={() => onSelect(key, target)}
        />
      ))}
    </Stack>
  );
}

export default function App() {
  const { t } = useLanguage();
  const [origin, setOrigin] = useState({
    ...WARSAW_PRESETS.centrum,
    label: "",
  });
  const [destination, setDestination] = useState({
    ...WARSAW_PRESETS.mokotow,
    label: "",
  });
  const [pickTarget, setPickTarget] = useState("origin");
  const [departureAt, setDepartureAt] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);
  const [activeMode, setActiveMode] = useState(null);

  const departureDefault = useMemo(() => {
    const now = new Date();
    now.setSeconds(0, 0);
    const offset = now.getTimezoneOffset();
    const local = new Date(now.getTime() - offset * 60_000);
    return local.toISOString().slice(0, 16);
  }, []);

  function handleMapClick(lat, lon, target) {
    const point = { lat, lon, label: "" };
    if (target === "origin") {
      setOrigin(point);
    } else {
      setDestination(point);
    }
  }

  async function handleSubmit(event) {
    event.preventDefault();
    setLoading(true);
    setError(null);
    setActiveMode(null);

    try {
      const comparison = await compareRoutes({
        origin_lat: origin.lat,
        origin_lon: origin.lon,
        destination_lat: destination.lat,
        destination_lon: destination.lon,
        departure_at: departureAt || undefined,
      });
      setResult(comparison);
      setActiveMode(comparison.best_option?.mode ?? null);
    } catch (submitError) {
      setResult(null);
      setError(
        submitError instanceof Error ? submitError.message : t("form.unknownError"),
      );
    } finally {
      setLoading(false);
    }
  }

  function applyPreset(presetKey, target) {
    const point = WARSAW_PRESETS[presetKey];
    const presetLabel = t(`presets.${presetKey}`);
    if (target === "origin") {
      setOrigin({ lat: point.lat, lon: point.lon, label: presetLabel });
    } else {
      setDestination({ lat: point.lat, lon: point.lon, label: presetLabel });
    }
  }

  return (
    <Container maxWidth="lg" sx={{ py: { xs: 3, md: 5 } }}>
      <Stack
        direction={{ xs: "column", sm: "row" }}
        justifyContent="space-between"
        alignItems={{ xs: "flex-start", sm: "center" }}
        spacing={2}
        sx={{ mb: 3 }}
      >
        <Box>
          <Typography
            variant="overline"
            color="text.secondary"
            sx={{ fontFamily: '"IBM Plex Mono", monospace', letterSpacing: "0.12em" }}
          >
            {t("app.overline")}
          </Typography>
          <Typography variant="h3" component="h1" sx={{ mt: 0.5 }}>
            {t("app.title")}
          </Typography>
          <Typography variant="body1" color="text.secondary" sx={{ mt: 1, maxWidth: 560 }}>
            {t("app.subtitle")}
          </Typography>
        </Box>
        <LanguageSwitcher />
      </Stack>

      <Card variant="outlined" sx={{ mb: 2.5, overflow: "hidden" }}>
        <Box sx={{ height: { xs: 320, md: 420 }, position: "relative" }}>
          <RouteMap
            origin={origin}
            destination={destination}
            pickTarget={pickTarget}
            onMapClick={handleMapClick}
            result={result}
            activeMode={activeMode}
          />
        </Box>
      </Card>

      <Grid container spacing={2.5}>
        <Grid size={{ xs: 12, md: 4 }}>
          <Card component="form" onSubmit={handleSubmit} variant="outlined">
            <CardContent>
              <Typography variant="h6" gutterBottom>
                {t("form.route")}
              </Typography>

              <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
                {t("form.mapHint")}
              </Typography>

              <Stack spacing={1.5} sx={{ mb: 2 }}>
                <AddressSearch
                  label={t("addressSearch.origin")}
                  value={origin}
                  onChange={setOrigin}
                  icon={PlaceIcon}
                />
                <AddressSearch
                  label={t("addressSearch.destination")}
                  value={destination}
                  onChange={setDestination}
                  icon={FlagIcon}
                />
              </Stack>

              <ToggleButtonGroup
                exclusive
                fullWidth
                size="small"
                value={pickTarget}
                onChange={(_event, value) => value && setPickTarget(value)}
                sx={{ mb: 2 }}
              >
                <ToggleButton value="origin">
                  <PlaceIcon fontSize="small" sx={{ mr: 0.75 }} />
                  {t("form.pickOrigin")}
                </ToggleButton>
                <ToggleButton value="destination">
                  <FlagIcon fontSize="small" sx={{ mr: 0.75 }} />
                  {t("form.pickDestination")}
                </ToggleButton>
              </ToggleButtonGroup>

              <Stack spacing={0.5} sx={{ mb: 2 }}>
                <Typography variant="caption" color="text.secondary">
                  {t("form.coordsOrigin")}:{" "}
                  {origin.label || `${origin.lat.toFixed(4)}, ${origin.lon.toFixed(4)}`}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  {t("form.coordsDestination")}:{" "}
                  {destination.label ||
                    `${destination.lat.toFixed(4)}, ${destination.lon.toFixed(4)}`}
                </Typography>
              </Stack>

              <Typography variant="subtitle2" color="text.secondary" sx={{ mb: 0.5 }}>
                {t("form.quickPresets")}
              </Typography>
              <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 0.25 }}>
                {t("form.presetForOrigin")}
              </Typography>
              <PresetChips target="origin" onSelect={applyPreset} />
              <Typography
                variant="caption"
                color="text.secondary"
                display="block"
                sx={{ mt: 1, mb: 0.25 }}
              >
                {t("form.presetForDestination")}
              </Typography>
              <PresetChips target="destination" onSelect={applyPreset} />

              <Divider sx={{ my: 2.5 }} />

              <TextField
                label={t("form.departureOptional")}
                type="datetime-local"
                value={departureAt}
                onChange={(e) => setDepartureAt(e.target.value)}
                fullWidth
                size="small"
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
                    <span>{t("form.searching")}</span>
                  </Stack>
                ) : (
                  t("form.compare")
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
          <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1 }}>
            <Typography variant="h6">{t("results.title")}</Typography>
            {result && activeMode && (
              <Chip
                label={t("results.showAllRoutes")}
                size="small"
                variant="outlined"
                onClick={() => setActiveMode(null)}
              />
            )}
          </Stack>

          {!result && !loading && (
            <Typography color="text.secondary">{t("results.emptyHint")}</Typography>
          )}

          {result && (
            <Stack spacing={1.5}>
              {result.options.map((option) => (
                <OptionCard
                  key={option.mode}
                  option={option}
                  highlighted={result.best_option?.mode === option.mode}
                  selected={activeMode === option.mode}
                  onSelect={setActiveMode}
                />
              ))}
            </Stack>
          )}
        </Grid>
      </Grid>
    </Container>
  );
}
