import { useEffect, useMemo, useState } from "react";
import Autocomplete from "@mui/material/Autocomplete";
import CircularProgress from "@mui/material/CircularProgress";
import TextField from "@mui/material/TextField";
import { searchAddresses } from "./geocoding";
import { useLanguage } from "./language/LanguageContext";

const MIN_QUERY_LENGTH = 3;
const DEBOUNCE_MS = 400;

function useDebouncedValue(value, delayMs) {
  const [debounced, setDebounced] = useState(value);

  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), delayMs);
    return () => window.clearTimeout(timer);
  }, [value, delayMs]);

  return debounced;
}

export default function AddressSearch({ label, value, onChange, icon: Icon }) {
  const { locale, t } = useLanguage();
  const [inputValue, setInputValue] = useState(value?.label ?? "");
  const [options, setOptions] = useState([]);
  const [loading, setLoading] = useState(false);
  const [searchError, setSearchError] = useState(null);
  const debouncedInput = useDebouncedValue(inputValue, DEBOUNCE_MS);

  const selectedOption = useMemo(() => {
    if (!value?.label) {
      return null;
    }
    return {
      label: value.label,
      lat: value.lat,
      lon: value.lon,
    };
  }, [value]);

  useEffect(() => {
    setInputValue(value?.label ?? "");
  }, [value?.label]);

  useEffect(() => {
    const trimmed = debouncedInput.trim();
    if (trimmed.length < MIN_QUERY_LENGTH) {
      setOptions([]);
      setLoading(false);
      setSearchError(null);
      return;
    }

    if (selectedOption && trimmed === selectedOption.label) {
      setOptions(selectedOption ? [selectedOption] : []);
      setLoading(false);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setSearchError(null);

    searchAddresses(trimmed, locale)
      .then((results) => {
        if (!cancelled) {
          setOptions(results);
        }
      })
      .catch((error) => {
        if (!cancelled) {
          setOptions([]);
          setSearchError(
            error instanceof Error ? error.message : t("addressSearch.unknownError"),
          );
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [debouncedInput, locale, selectedOption, t]);

  return (
    <Autocomplete
      freeSolo={false}
      fullWidth
      size="small"
      options={options}
      loading={loading}
      value={selectedOption}
      inputValue={inputValue}
      filterOptions={(items) => items}
      getOptionLabel={(option) => option.label}
      isOptionEqualToValue={(option, selected) =>
        option.label === selected.label &&
        option.lat === selected.lat &&
        option.lon === selected.lon
      }
      noOptionsText={
        inputValue.trim().length < MIN_QUERY_LENGTH
          ? t("addressSearch.typeToSearch")
          : t("addressSearch.noResults")
      }
      onInputChange={(_event, newInputValue, reason) => {
        if (reason === "reset") {
          return;
        }
        setInputValue(newInputValue);
      }}
      onChange={(_event, option) => {
        if (!option) {
          onChange({ lat: value?.lat, lon: value?.lon });
          return;
        }
        onChange({
          lat: option.lat,
          lon: option.lon,
          label: option.label,
        });
      }}
      renderInput={(params) => (
        <TextField
          {...params}
          label={label}
          error={Boolean(searchError)}
          helperText={searchError}
          slotProps={{
            input: {
              ...params.InputProps,
              startAdornment: Icon ? (
                <>
                  <Icon fontSize="small" color="action" sx={{ mr: 1 }} />
                  {params.InputProps.startAdornment}
                </>
              ) : (
                params.InputProps.startAdornment
              ),
              endAdornment: (
                <>
                  {loading ? <CircularProgress color="inherit" size={18} /> : null}
                  {params.InputProps.endAdornment}
                </>
              ),
            },
          }}
        />
      )}
    />
  );
}
