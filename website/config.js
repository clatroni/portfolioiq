// Portfolio IQ front-end config. Empty by default => the "Ask the AI" widget uses the
// offline scripted fallback. To enable the real Microsoft Fabric data agent, fill these in
// (see config.example.js for guidance).
window.PIQ_CONFIG = {
  clientId: "",
  tenantId: "",
  scope: "https://analysis.windows.net/powerbi/api/.default",
  redirectUri: "",

  // Where to read the dashboard JSON that Fabric publishes. Leave blank to use the
  // bundled public/data/. Set to the Fabric-published store base URL, e.g.
  //   "https://<account>.blob.core.windows.net/portfolioiq"
  // (the container must allow public/anonymous read or be fronted by a CDN, and have
  // CORS enabled for this site's origin). The site reads manifest.json + <ymd>.json there.
  dataBaseUrl: "",
};
