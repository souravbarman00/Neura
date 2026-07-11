export type Role = "user" | "ai";

export interface Source {
  source: string;
  name: string;
  score?: string | null;
}

export interface AgentMsg {
  agent: string;
  text: string;
  kind?: string; // "say" | "result"
  path?: string[];
}

export interface CommandRun {
  command: string;
  exit: number;
  output: string;
}

export interface Message {
  id: string;
  role: Role;
  text: string;
  sources?: Source[];
  build?: string; // capability description if Neura suggested building an agent
  trace?: AgentMsg[]; // agent-to-agent talk behind this answer (the "thinking")
  commands?: CommandRun[]; // shell commands the codebase agent ran (terminal cards)
}

export interface Health {
  status: string;
  runtime: boolean;
  network: string;
  kb_chunks: number;
  agents: unknown[];
}
