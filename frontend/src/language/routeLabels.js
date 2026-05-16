export function getParkAndRideParkingName(option) {
  return (
    option.details?.park_and_ride?.parking?.name ??
    option.label?.replace(/^Park & Ride:\s*/i, "") ??
    ""
  );
}

export function getOptionDisplayLabel(option, t) {
  if (option.mode === "park_and_ride") {
    const name = getParkAndRideParkingName(option);
    return t("modes.park_and_ride", { name });
  }

  if (option.mode === "car") {
    return t("modes.car");
  }

  if (option.mode === "public_transport") {
    return t("modes.public_transport");
  }

  return option.label;
}

export function getOptionReason(option, t) {
  if (option.available) {
    return null;
  }

  const key = `errors.${option.mode}`;
  const translated = t(key);
  return translated === key ? option.reason : translated;
}

export function translateLegPlaceName(name, t) {
  if (name === "origin") {
    return t("leg.origin");
  }
  if (name === "destination") {
    return t("leg.destination");
  }
  return name;
}
