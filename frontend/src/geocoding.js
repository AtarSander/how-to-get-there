export async function searchAddresses(query, lang = "pl") {
  const params = new URLSearchParams({ q: query, lang });
  const response = await fetch(`/api/geocode/search?${params.toString()}`);
  const data = await response.json();

  if (!response.ok) {
    const message =
      typeof data?.error === "string" ? data.error : "Address search failed.";
    throw new Error(message);
  }

  return data.results ?? [];
}
