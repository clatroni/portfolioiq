// Portfolio IQ — "Ask the AI" backend: proxy to a published Microsoft Fabric data agent.
//
// The published Fabric data agent speaks the OpenAI Assistants API (assistant -> thread ->
// message -> run -> poll -> read) at its published base URL. Fabric data agents support
// USER IDENTITY ONLY (no service principal), so this proxy does NOT hold a secret: the
// browser signs the user in with MSAL and sends the user's bearer token, which we forward
// to Fabric. RLS on the semantic model is therefore enforced per signed-in user.
//
// Why a proxy at all (vs calling Fabric straight from the browser): avoids cross-origin
// (CORS) calls to fabric.microsoft.com and keeps the multi-step Assistants polling loop
// server-side.
//
// Environment variables (Vercel → Settings → Environment Variables):
//   FABRIC_DATA_AGENT_URL    the published base URL of the data agent (from Fabric → data
//                            agent → Settings → published URL). Required.
//   FABRIC_API_VERSION       optional, default 2024-05-01-preview
//   FABRIC_RUN_TIMEOUT_MS    optional, default 60000
//
// Reference: https://learn.microsoft.com/en-us/fabric/data-science/data-agent-end-to-end-tutorial
// NOTE: the Assistants-API surface is deprecated by Fabric with a shutdown date of
// 2026-08-26; migrate to the MCP endpoint before then.

function send(res, status, obj) {
  res.statusCode = status;
  res.setHeader("Content-Type", "application/json");
  res.setHeader("Cache-Control", "no-store");
  res.end(JSON.stringify(obj));
}

async function readJsonBody(req) {
  if (req.body) return typeof req.body === "string" ? JSON.parse(req.body) : req.body;
  const chunks = [];
  for await (const c of req) chunks.push(c);
  return JSON.parse(Buffer.concat(chunks).toString("utf8") || "{}");
}

function uuid() {
  // RFC4122-ish v4, sufficient for an ActivityId correlation header.
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    return (c === "x" ? r : (r & 0x3) | 0x8).toString(16);
  });
}

module.exports = async (req, res) => {
  if (req.method !== "POST") return send(res, 405, { error: "Method not allowed" });

  const base = (process.env.FABRIC_DATA_AGENT_URL || "").replace(/\/+$/, "");
  const apiVersion = process.env.FABRIC_API_VERSION || "2024-05-01-preview";
  const runTimeout = parseInt(process.env.FABRIC_RUN_TIMEOUT_MS || "60000", 10);
  if (!base) return send(res, 503, { error: "Data agent not configured" }); // -> client falls back

  // User's delegated Fabric token, forwarded from the browser (MSAL). No SPN.
  const auth = req.headers["authorization"];
  if (!auth || !/^Bearer\s+/i.test(auth)) {
    return send(res, 401, { error: "Sign-in required" }); // -> client prompts sign-in / falls back
  }

  let body;
  try {
    body = await readJsonBody(req);
  } catch {
    return send(res, 400, { error: "Invalid JSON body" });
  }
  const question = (body.question || "").toString().slice(0, 1500).trim();
  if (!question) return send(res, 400, { error: "Missing question" });

  const headers = {
    Authorization: auth,
    "Content-Type": "application/json",
    Accept: "application/json",
    "OpenAI-Beta": "assistants=v2",
    ActivityId: uuid(),
  };
  const q = `?api-version=${encodeURIComponent(apiVersion)}`;
  const api = (path) => `${base}${path}${q}`;

  async function call(method, path, payload) {
    const r = await fetch(api(path), {
      method,
      headers,
      body: payload ? JSON.stringify(payload) : undefined,
    });
    if (!r.ok) {
      const detail = await r.text().catch(() => "");
      const err = new Error(`Fabric ${method} ${path} -> ${r.status}`);
      err.status = r.status;
      err.detail = detail.slice(0, 600);
      throw err;
    }
    return r.status === 204 ? {} : r.json();
  }

  let threadId = null;
  try {
    // 1) assistant (model field is unused by Fabric), 2) thread, 3) message, 4) run
    const assistant = await call("POST", "/assistants", { model: "not used" });
    const thread = await call("POST", "/threads", {});
    threadId = thread.id;
    await call("POST", `/threads/${threadId}/messages`, { role: "user", content: question });
    let run = await call("POST", `/threads/${threadId}/runs`, { assistant_id: assistant.id });

    // 5) poll to terminal state
    const terminal = new Set(["completed", "failed", "cancelled", "expired", "requires_action"]);
    const start = Date.now();
    while (!terminal.has(run.status)) {
      if (Date.now() - start > runTimeout) {
        return send(res, 504, { error: "Agent run timed out", status: run.status });
      }
      await new Promise((r) => setTimeout(r, 2000));
      run = await call("GET", `/threads/${threadId}/runs/${run.id}`);
    }
    if (run.status !== "completed") {
      return send(res, 502, { error: "Agent run did not complete", status: run.status });
    }

    // 6) read the latest assistant message
    const msgs = await call("GET", `/threads/${threadId}/messages?order=desc&limit=10`);
    const list = (msgs && msgs.data) || [];
    const aiMsg = list.find((m) => m.role === "assistant");
    const text =
      aiMsg && aiMsg.content && aiMsg.content[0] && aiMsg.content[0].text
        ? aiMsg.content[0].text.value
        : null;
    if (!text) return send(res, 502, { error: "No answer returned" });

    return send(res, 200, { answer: text });
  } catch (e) {
    const status = e.status === 401 || e.status === 403 ? e.status : 502;
    return send(res, status, { error: "Fabric data agent error", detail: e.detail || e.message });
  } finally {
    // 7) best-effort cleanup so threads don't accumulate on the agent
    if (threadId) {
      try {
        await fetch(api(`/threads/${threadId}`), { method: "DELETE", headers });
      } catch {
        /* ignore cleanup failure */
      }
    }
  }
};
