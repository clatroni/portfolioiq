// Portfolio IQ — front-end config for the Microsoft Fabric data agent sign-in.
//
// Copy this file to `config.js` and fill in the values. When `config.js` has all four
// fields, the "Ask the AI" widget signs the user in (MSAL popup) and calls the published
// Fabric data agent through /api/ask. If any field is blank, the widget falls back to the
// built-in scripted answers.
//
// These values are NOT secrets — a public SPA exposes its clientId/tenantId by design.
// The actual data access is gated by the user's sign-in and the semantic model's RLS.

window.PIQ_CONFIG = {
  // Application (client) ID of the Entra app registration you create for this site (SPA).
  clientId: "00000000-0000-0000-0000-000000000000",

  // Your Entra tenant (directory) ID.
  tenantId: "00000000-0000-0000-0000-000000000000",

  // Delegated scope used to call the Fabric data agent. Power BI semantic-model agents
  // typically use the Power BI service scope; if you get 401s, try the Fabric scope.
  //   Power BI:  "https://analysis.windows.net/powerbi/api/.default"
  //   Fabric:    "https://api.fabric.microsoft.com/.default"
  scope: "https://analysis.windows.net/powerbi/api/.default",

  // Optional. Defaults to the current site origin. Must be registered as a SPA redirect URI.
  redirectUri: "",
};
