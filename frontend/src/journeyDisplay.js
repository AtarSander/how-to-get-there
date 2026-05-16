function normalizeLeg(leg, mode = leg.mode) {
  return {
    mode,
    from_name: leg.from_name,
    to_name: leg.to_name,
    departure_at: leg.departure_at,
    arrival_at: leg.arrival_at,
    route_name: leg.route_name ?? null,
    trip_headsign: leg.trip_headsign ?? null,
    duration_minutes: leg.duration_minutes ?? null,
  };
}

export function collectDisplayLegs(option) {
  if (!option.available || !option.details) {
    return null;
  }

  if (option.mode === "public_transport") {
    const legs = option.details.public_transport?.legs;
    return legs?.length ? legs.map((leg) => normalizeLeg(leg)) : null;
  }

  if (option.mode === "park_and_ride") {
    const route = option.details.park_and_ride;
    if (!route) {
      return null;
    }

    const legs = [];
    const car = route.car_route;
    if (car?.departure_at && car?.arrival_at) {
      legs.push({
        mode: "car",
        from_name: "origin",
        to_name: route.parking?.name ?? "P+R",
        departure_at: car.departure_at,
        arrival_at: car.arrival_at,
        route_name: null,
        trip_headsign: null,
        duration_minutes: car.total_minutes ?? null,
      });
    }

    const walk = route.walk_to_metro;
    if (walk?.departure_at && walk?.arrival_at) {
      legs.push(normalizeLeg({ ...walk, mode: "walk" }));
    }

    const ptLegs = route.public_transport?.legs ?? [];
    for (const leg of ptLegs) {
      legs.push(normalizeLeg(leg));
    }

    return legs.length ? legs : null;
  }

  return null;
}

export function minutesBetween(arrivalIso, departureIso) {
  if (!arrivalIso || !departureIso) {
    return null;
  }
  const diffMs = new Date(departureIso).getTime() - new Date(arrivalIso).getTime();
  return Math.max(0, Math.round(diffMs / 60_000));
}

export function buildJourneyTimeline(legs) {
  const items = [];

  for (let index = 0; index < legs.length; index += 1) {
    items.push({ type: "leg", leg: legs[index], index });

    const current = legs[index];
    const next = legs[index + 1];
    if (!next) {
      continue;
    }

    if (current.mode === "ride" && next.mode === "ride") {
      items.push({
        type: "transfer",
        stopName: current.to_name,
        arrivalAt: current.arrival_at,
        departureAt: next.departure_at,
        waitMinutes: minutesBetween(current.arrival_at, next.departure_at),
      });
    }
  }

  return items;
}

export function formatLegModeLabel(leg, t) {
  if (leg.mode === "walk") {
    return t("leg.modeWalk");
  }
  if (leg.mode === "car") {
    return t("leg.modeCar");
  }
  if (leg.mode === "ride") {
    return leg.route_name ? `${t("leg.modeRide")} ${leg.route_name}` : t("leg.modeRide");
  }
  return null;
}
