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

export interface FileChange {
  path: string;
  diff: string; // unified diff text
  kind?: string; // "edit" | "create" | "overwrite"
}

// One item in the chronological turn timeline (thinking / command / file diff), in the
// exact order it happened, so the UI can stream it live and keep it time-ordered.
export interface TurnEvent {
  t: "trace" | "cmd" | "diff";
  agent?: string; text?: string; kind?: string; // trace
  command?: string; exit?: number; output?: string; // cmd
  path?: string; diff?: string; changeKind?: string; // diff
}

export interface Message {
  id: string;
  role: Role;
  text: string;
  sources?: Source[];
  build?: string; // capability description if Neura suggested building an agent
  trace?: AgentMsg[]; // agent-to-agent talk behind this answer (the "thinking")
  commands?: CommandRun[]; // shell commands the codebase agent ran (terminal cards)
  fileChanges?: FileChange[]; // file edits/creates the codebase agent made (diff cards)
  events?: TurnEvent[]; // chronological command + diff cards (in-session; for time-ordered display)
}

export interface Health {
  status: string;
  runtime: boolean;
  network: string;
  kb_chunks: number;
  agents: unknown[];
}
