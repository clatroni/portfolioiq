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

  // Power BI report behind the dashboard. When set, "View source Power BI dashboard ↗"
  // opens it in a new tab; blank keeps the link disabled.
  pbiReportUrl: "https://app.fabric.microsoft.com/groups/bdbe81c9-1aa3-442a-932b-08ebab8991d2/reports/4e7d94e3-24f0-4c2b-b2a5-b8a677b157ea/cb1980ce1d686830c013?ctid=0435f515-1d02-4e55-9c28-bb4e32bd21d7&experience=fabric-developer",
};
