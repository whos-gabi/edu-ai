type AgentConfig = {
  url?: string;
  apiKey?: string;
  phone?: string;
};

function resolveAgentUrl(rawUrl?: string): string {
  const trimmed = rawUrl?.trim();
  if (!trimmed) {
    throw new Error("Missing AGENT_API_URL.");
  }
  if (trimmed.endsWith("/chat")) {
    return trimmed;
  }
  return `${trimmed.replace(/\/+$/, "")}/chat`;
}

export async function agentReply(
  _prompt: string,
  _cfg: AgentConfig
): Promise<string> {
  const url = resolveAgentUrl(_cfg.url);
  const phone = _cfg.phone ?? "";
  const phoneKind = phone.startsWith("+")
    ? "phone_like"
    : /^[0-9]+$/.test(phone)
    ? "digits_only"
    : "other";

  // #region debug log H5
  fetch("http://127.0.0.1:7242/ingest/6f0a844a-d53d-4ddc-b246-3444195ce1ea", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      sessionId: "debug-session",
      runId: "pre-fix",
      hypothesisId: "H5",
      location: "agentClient.ts:agentReply",
      message: "agent_reply_outbound",
      data: {
        url_present: Boolean(_cfg.url?.trim()),
        url_has_chat: url.endsWith("/chat"),
        has_api_key: Boolean(_cfg.apiKey),
        phone_kind: phoneKind,
        phone_len: phone.length,
        message_len: _prompt.length,
      },
      timestamp: Date.now(),
    }),
  }).catch(() => {});
  // #endregion

  const res = await fetch(url, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      ...(_cfg.apiKey ? { "x-api-key": _cfg.apiKey } : {}),
    },
    body: JSON.stringify({ phone, message: _prompt }),
  });

  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`Agent API error ${res.status}: ${body}`);
  }

  const data = (await res.json()) as { reply?: string };
  return data.reply ?? "";
}

