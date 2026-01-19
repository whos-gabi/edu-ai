type AgentConfig = {
  url?: string;
  apiKey?: string;
};

export async function agentReply(
  _prompt: string,
  _cfg: AgentConfig
): Promise<string> {
  // Future: call your Agent_API here (HTTP).
  // This demo bot just returns a placeholder.
  return "Agent API is not connected yet (demo auth is working).";
}

