export const translations = {
  pl: {
    app: {
      overline: "Warszawa · SPDB",
      title: "Jak tam dojechać?",
      subtitle:
        "Wyszukaj adres lub kliknij mapę, aby ustawić start i cel. Porównaj samochód, komunikację miejską i Park & Ride.",
    },
    locale: {
      pl: "Polski",
      en: "English",
    },
    map: {
      start: "Start",
      destination: "Cel",
    },
    addressSearch: {
      origin: "Adres startu",
      destination: "Adres celu",
      typeToSearch: "Wpisz co najmniej 3 znaki…",
      noResults: "Brak wyników",
      unknownError: "Nie udało się wyszukać adresu.",
    },
    form: {
      route: "Trasa",
      mapHint: "Wyszukaj adres poniżej albo wybierz punkt na mapie.",
      pickOrigin: "Start na mapie",
      pickDestination: "Cel na mapie",
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
      emptyHint: "Ustaw start i cel (wyszukiwarka lub mapa), potem uruchom porównanie.",
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
      modeWalk: "Pieszo",
      modeCar: "Samochód",
      modeRide: "Kurs",
      transferAt: "Przesiadka: {{stop}}",
      transferWait: "przyjazd {{arrival}}, odjazd {{departure}} ({{minutes}} min)",
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
        "Search for an address or click the map to set start and destination. Compare car, public transport, and Park & Ride.",
    },
    locale: {
      pl: "Polish",
      en: "English",
    },
    map: {
      start: "Start",
      destination: "Destination",
    },
    addressSearch: {
      origin: "Start address",
      destination: "Destination address",
      typeToSearch: "Type at least 3 characters…",
      noResults: "No results",
      unknownError: "Address search failed.",
    },
    form: {
      route: "Route",
      mapHint: "Search for an address below or pick a point on the map.",
      pickOrigin: "Set start on map",
      pickDestination: "Set destination on map",
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
      emptyHint: "Set start and destination (search or map), then run comparison.",
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
      modeWalk: "Walk",
      modeCar: "Car",
      modeRide: "Ride",
      transferAt: "Transfer at {{stop}}",
      transferWait: "arrive {{arrival}}, depart {{departure}} ({{minutes}} min)",
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
