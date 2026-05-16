import { Fragment, useEffect, useMemo } from "react";
import {
  CircleMarker,
  MapContainer,
  Polyline,
  TileLayer,
  Tooltip,
  useMap,
} from "react-leaflet";
import { useLanguage } from "./language/LanguageContext";
import {
  LINE_KIND_COLORS,
  MARKER_KIND_COLORS,
  MODE_LINE_COLORS,
} from "./mapColors";

const WARSAW_CENTER = [52.2297, 21.0122];
const DEFAULT_ZOOM = 11;

function FitBounds({ positions }) {
  const map = useMap();

  useEffect(() => {
    if (!positions.length) {
      return;
    }
    map.fitBounds(positions, { padding: [48, 48] });
  }, [map, positions]);

  return null;
}

function collectAllPositions(origin, destination, result, activeMode) {
  const positions = [];
  if (origin) {
    positions.push([origin.lat, origin.lon]);
  }
  if (destination) {
    positions.push([destination.lat, destination.lon]);
  }

  if (!result) {
    return positions;
  }

  for (const option of result.options) {
    if (!option.available || !option.map) {
      continue;
    }
    if (activeMode && option.mode !== activeMode) {
      continue;
    }
    for (const line of option.map.lines) {
      for (const point of line.positions) {
        positions.push(point);
      }
    }
    for (const marker of option.map.markers ?? []) {
      positions.push([marker.lat, marker.lon]);
    }
  }

  return positions;
}

export default function RouteMap({
  origin,
  destination,
  pickTarget,
  onMapClick,
  result,
  activeMode,
}) {
  const { t } = useLanguage();
  const fitPositions = useMemo(
    () => collectAllPositions(origin, destination, result, activeMode),
    [origin, destination, result, activeMode],
  );

  return (
    <MapContainer
      center={WARSAW_CENTER}
      zoom={DEFAULT_ZOOM}
      style={{ height: "100%", width: "100%", borderRadius: 12 }}
      scrollWheelZoom
    >
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />

      <FitBounds positions={fitPositions} />

      {result?.options.map((option) => {
        if (!option.available || !option.map) {
          return null;
        }

        const isActive = !activeMode || activeMode === option.mode;
        const modeColor = MODE_LINE_COLORS[option.mode] ?? "#90caf9";

        return (
          <Fragment key={option.mode}>
            {option.map.lines.map((line, index) => (
              <Polyline
                key={`${option.mode}-${line.kind}-${index}`}
                positions={line.positions}
                pathOptions={{
                  color: isActive
                    ? LINE_KIND_COLORS[line.kind] ?? modeColor
                    : "#546e7a",
                  weight: isActive ? 5 : 3,
                  opacity: isActive ? 0.9 : 0.25,
                  dashArray:
                    isActive && line.kind === "walk"
                      ? "6 8"
                      : undefined,
                }}
              />
            ))}
            {(option.map.markers ?? []).map((marker, index) => {
              const markerColors = MARKER_KIND_COLORS[marker.kind] ?? {
                color: modeColor,
                fillColor: modeColor,
              };
              const isTransitStop = marker.kind === "transit_stop";

              return (
                <CircleMarker
                  key={`${option.mode}-${marker.kind}-${marker.label}-${index}`}
                  center={[marker.lat, marker.lon]}
                  radius={isTransitStop ? 5 : 7}
                  pathOptions={{
                    color: markerColors.color,
                    fillColor: markerColors.fillColor,
                    fillOpacity: isActive ? 0.92 : 0.35,
                    opacity: isActive ? 1 : 0.35,
                    weight: isTransitStop ? 2.5 : 2,
                  }}
                >
                  <Tooltip>{marker.label}</Tooltip>
                </CircleMarker>
              );
            })}
          </Fragment>
        );
      })}

      {origin && (
        <CircleMarker
          center={[origin.lat, origin.lon]}
          radius={9}
          pathOptions={{
            color: "#66bb6a",
            fillColor: "#66bb6a",
            fillOpacity: 0.95,
            weight: 2,
          }}
        >
          <Tooltip>{t("map.start")}</Tooltip>
        </CircleMarker>
      )}

      {destination && (
        <CircleMarker
          center={[destination.lat, destination.lon]}
          radius={9}
          pathOptions={{
            color: "#ef5350",
            fillColor: "#ef5350",
            fillOpacity: 0.95,
            weight: 2,
          }}
        >
          <Tooltip>{t("map.destination")}</Tooltip>
        </CircleMarker>
      )}

      <MapClickHandler pickTarget={pickTarget} onMapClick={onMapClick} />
    </MapContainer>
  );
}

function MapClickHandler({ pickTarget, onMapClick }) {
  const map = useMap();

  useEffect(() => {
    function handleClick(event) {
      onMapClick(event.latlng.lat, event.latlng.lng, pickTarget);
    }

    map.on("click", handleClick);
    return () => {
      map.off("click", handleClick);
    };
  }, [map, onMapClick, pickTarget]);

  return null;
}
