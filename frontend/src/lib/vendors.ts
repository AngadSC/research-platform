/** Search links for the new-order dialog. Checked with plain requests on 2026-11-09:
 * Thermo Fisher answered 200 with its search page (the term is rendered client-side). VWR's server
 * redirects `?keyword=` searches to this path. Fisher Scientific (403) and Sigma-Aldrich (no
 * response) refused scripted requests, so their formats are unverified: try them in a browser. */
const VENDORS = [
  {
    name: "Thermo Fisher",
    search: (q: string) => `https://www.thermofisher.com/search/results?query=${q}`,
  },
  {
    name: "Fisher Scientific",
    search: (q: string) => `https://www.fishersci.com/us/en/catalog/search/products?keyword=${q}`,
  },
  {
    name: "Sigma-Aldrich",
    search: (q: string) => `https://www.sigmaaldrich.com/CA/en/search/${q}?term=${q}&type=product`,
  },
  {
    name: "VWR",
    // an encoded slash in this path is a 404, and it is only a separator in a search term
    search: (q: string) => `https://www.vwr.com/ca/en/search/${q.replaceAll("%2F", "%20")}`,
  },
];

export const vendorLinks = (term: string) =>
  VENDORS.map((v) => ({ name: v.name, href: v.search(encodeURIComponent(term)) }));
