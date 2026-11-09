/**
 * Minimal result relay for grokbot-x-mcp-bridge.
 * Cloud box POSTs /result; always-on gateway GETs /response/:id.
 * Bind a KV namespace as RESULTS.
 */
export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const auth = request.headers.get("Authorization") || "";
    const expected = env.RELAY_TOKEN ? `Bearer ${env.RELAY_TOKEN}` : "";
    if (expected && auth !== expected) {
      return json({ error: "unauthorized" }, 401);
    }

    if (request.method === "GET" && url.pathname === "/health") {
      return json({ ok: true, service: "grokbot-x-relay" });
    }

    if (request.method === "POST" && url.pathname === "/result") {
      const body = await request.json();
      const id = String(body.req_id || "");
      if (!/^[0-9]{10,}-[0-9a-f]{6,}$/i.test(id)) {
        return json({ error: "bad_req_id" }, 400);
      }
      await env.RESULTS.put(id, JSON.stringify({ ready: true, result: body.result }), { expirationTtl: 900 });
      return json({ saved: true, req_id: id });
    }

    const m = url.pathname.match(/^\/response\/([^/]+)$/);
    if (request.method === "GET" && m) {
      const raw = await env.RESULTS.get(m[1]);
      if (!raw) return json({ ready: false }, 404);
      return new Response(raw, { status: 200, headers: { "Content-Type": "application/json" } });
    }

    return json({ error: "not_found" }, 404);
  },
};

function json(obj, status = 200) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}
