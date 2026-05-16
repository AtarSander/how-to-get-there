export const translations = {
  pl: {
    app: {
      overline: "Warszawa · SPDB",
      title: "Jak tam dojechać?",
      subtitle:
        "Kliknij mapę, aby ustawić start i cel. Porównaj samochód, komunikację miejską i Park & Ride.",
    },
    locale: {
      pl: "Polski",
      en: "English",
    },
    map: {
      start: "Start",
      destination: "Cel",
    },
    form: {
      route: "Trasa",
      mapHint: "Wybierz, co ustawiasz na mapie, i kliknij punkt.",
      pickOrigin: "Start",
      pickDestination: "Cel",
      coordsOrigin: "Start",
      coordsDestination: "Cel",
      quickPresets: "Szybkie presety",
      departureOptional: "Wyjazd (opcjonalnie)",
      compare: "Porównaj opcje",
      searching: "Szukam tras…",
      unknownError: "Nieznany błąd.",
    },
    results: {
      title: "Wyniki",
      showAllRoutes: "Pokaż wszystkie trasy",
      emptyHint: "Ustaw start i cel na mapie, potem uruchom porównanie.",
    },
    option: {
      fastest: "Najszybsza",
      duration: "Czas",
      departure: "Odjazd",
      arrival: "Przyjazd",
      distance: "Dystans",
      transfers: "Przesiadki",
      minutes: "min",
    },
    modes: {
      car: "Samochód",
      public_transport: "Komunikacja miejska",
      park_and_ride: "Park & Ride: {{name}}",
    },
    errors: {
      car: "Nie znaleziono trasy samochodowej.",
      public_transport: "Nie znaleziono połączenia komunikacją miejską.",
      park_and_ride: "Nie znaleziono trasy Park & Ride.",
    },
    leg: {
      origin: "punkt startowy",
      destination: "cel",
    },
    presets: {
      centrum: "Centrum",
      wola: "Wola",
      praga: "Praga Północ",
      mokotow: "Mokotów",
    },
  },
  en: {
    app: {
      overline: "Warsaw · SPDB",
      title: "How to get there?",
      subtitle:
        "Click the map to set start and destination. Compare car, public transport, and Park & Ride.",
    },
    locale: {
      pl: "Polish",
      en: "English",
    },
    map: {
      start: "Start",
      destination: "Destination",
    },
    form: {
      route: "Route",
      mapHint: "Choose what you set on the map, then click a point.",
      pickOrigin: "Start",
      pickDestination: "Destination",
      coordsOrigin: "Start",
      coordsDestination: "Destination",
      quickPresets: "Quick presets",
      departureOptional: "Departure (optional)",
      compare: "Compare options",
      searching: "Searching routes…",
      unknownError: "Unknown error.",
    },
    results: {
      title: "Results",
      showAllRoutes: "Show all routes",
      emptyHint: "Set start and destination on the map, then run comparison.",
    },
    option: {
      fastest: "Fastest",
      duration: "Duration",
      departure: "Departure",
      arrival: "Arrival",
      distance: "Distance",
      transfers: "Transfers",
      minutes: "min",
    },
    modes: {
      car: "Car",
      public_transport: "Public transport",
      park_and_ride: "Park & Ride: {{name}}",
    },
    errors: {
      car: "No driving route found.",
      public_transport: "No public transport connection found.",
      park_and_ride: "No Park & Ride route found.",
    },
    leg: {
      origin: "origin",
      destination: "destination",
    },
    presets: {
      centrum: "City centre",
      wola: "Wola",
      praga: "Praga Północ",
      mokotow: "Mokotów",
    },
  },
};

export const LOCALE_STORAGE_KEY = "spdb-locale";

export const SUPPORTED_LOCALES = ["pl", "en"];
