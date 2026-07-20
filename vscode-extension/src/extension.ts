import * as vscode from "vscode";
import { TextDecoder } from "util";

/** Read the bundled Neura UI build and turn it into webview-ready HTML:
 *  - rewrite Vite's root-absolute asset refs (`/assets/…`) to `webview.asWebviewUri`
 *  - inject a CSP that permits the bundle + fetch/SSE + screenshots to the backend
 *  - inject the backend base URL and the open folder so the UI targets them */
async function buildHtml(
  webview: vscode.Webview,
  extensionUri: vscode.Uri
): Promise<string> {
  const mediaUri = vscode.Uri.joinPath(extensionUri, "media");
  const indexUri = vscode.Uri.joinPath(mediaUri, "index.html");
  let html: string;
  try {
    html = new TextDecoder().decode(await vscode.workspace.fs.readFile(indexUri));
  } catch {
    return `<html><body style="font:14px system-ui;padding:24px;color:#c7ccd8;background:#0b0e15">
      <h3>Neura UI not bundled</h3>
      <p>The built UI is missing from <code>media/</code>. Run <code>npm run sync-ui</code> then reload.</p>
    </body></html>`;
  }

  const cfg = vscode.workspace.getConfiguration("neura");
  const base = (cfg.get<string>("backendUrl") || "http://127.0.0.1:8010").replace(/\/+$/, "");
  const autoWs = cfg.get<boolean>("autoWorkspace") !== false;
  const ws = autoWs ? vscode.workspace.workspaceFolders?.[0]?.uri.fsPath || "" : "";

  // Rewrite root-absolute asset references (src="/assets/…", href="/assets/…", favicon)
  // to webview resource URIs under media/.
  html = html.replace(/(src|href)="\/([^"]+)"/g, (_m, attr, path) => {
    const u = webview.asWebviewUri(vscode.Uri.joinPath(mediaUri, path));
    return `${attr}="${u}"`;
  });

  const csp = [
    `default-src 'none'`,
    `img-src ${webview.cspSource} ${base} data: blob: https:`,
    `media-src ${webview.cspSource} ${base} blob:`,
    `style-src ${webview.cspSource} 'unsafe-inline' https://fonts.googleapis.com`,
    `script-src ${webview.cspSource} 'unsafe-inline'`,
    `font-src ${webview.cspSource} data: https://fonts.gstatic.com`,
    `connect-src ${base} ws: wss:`,
    `frame-src ${base}`,
  ].join("; ");

  const inject =
    `<meta http-equiv="Content-Security-Policy" content="${csp}">` +
    `<script>window.__NEURA_API_BASE__=${JSON.stringify(base)};` +
    `window.__NEURA_WORKSPACE__=${JSON.stringify(ws)};` +
    `window.__NEURA_IN_VSCODE__=true;</script>`;

  // Put CSP + globals first in <head> so they apply before the bundle loads.
  html = html.includes("<head>")
    ? html.replace("<head>", `<head>${inject}`)
    : inject + html;
  return html;
}

function webviewOptions(extensionUri: vscode.Uri): vscode.WebviewOptions {
  return {
    enableScripts: true,
    localResourceRoots: [vscode.Uri.joinPath(extensionUri, "media")],
  };
}

/** Resolve the Neura project folder (with scripts/start_neura.sh), prompting once. */
async function resolveProjectPath(): Promise<string | undefined> {
  const cfg = vscode.workspace.getConfiguration("neura");
  let dir = (cfg.get<string>("projectPath") || "").trim();
  const hasScript = async (d: string) => {
    try {
      await vscode.workspace.fs.stat(vscode.Uri.file(`${d}/scripts/start_neura.sh`));
      return true;
    } catch {
      return false;
    }
  };
  if (dir && (await hasScript(dir))) return dir;

  // Try the open workspace folder if it looks like the Neura repo.
  const open = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
  if (open && (await hasScript(open))) {
    await cfg.update("projectPath", open, vscode.ConfigurationTarget.Global);
    return open;
  }

  const picked = await vscode.window.showOpenDialog({
    canSelectFolders: true,
    canSelectFiles: false,
    canSelectMany: false,
    openLabel: "Select the Neura project folder",
    title: "Neura project folder (contains scripts/start_neura.sh)",
  });
  dir = picked?.[0]?.fsPath || "";
  if (!dir) return undefined;
  if (!(await hasScript(dir))) {
    vscode.window.showErrorMessage(
      "That folder has no scripts/start_neura.sh — pick the Neura project root."
    );
    return undefined;
  }
  await cfg.update("projectPath", dir, vscode.ConfigurationTarget.Global);
  return dir;
}

/** Run the setup+start script in a dedicated terminal (installs deps, starts servers). */
async function startNeura() {
  const dir = await resolveProjectPath();
  if (!dir) return;
  const term =
    vscode.window.terminals.find((t) => t.name === "Neura") ||
    vscode.window.createTerminal({ name: "Neura", cwd: dir });
  term.show();
  term.sendText(`bash "${dir}/scripts/start_neura.sh"`);
  vscode.window.showInformationMessage(
    "Starting Neura… first run installs packages (can take a few minutes). The panel connects automatically once it's up."
  );
}

const HELP = `# Start Neura

**Start Neura** installs the Python packages and launches all servers (agent runtime, API, voice) in a terminal.

1. First run: pick your **Neura project folder** (the repo containing \`scripts/start_neura.sh\`).
2. It creates a virtualenv, installs requirements, and starts the servers. Keep that terminal open; **Ctrl-C** there stops Neura.
3. Add an LLM API key to the project's \`.env\` if prompted, e.g. \`ANTHROPIC_API_KEY=sk-ant-…\` or \`OPENAI_API_KEY=…\`, then Start again.

Change the backend URL or project folder in **Settings → Extensions → Neura**.`;

function wireMessages(webview: vscode.Webview, context: vscode.ExtensionContext) {
  webview.onDidReceiveMessage(
    async (msg: any) => {
      if (msg?.type === "startNeura") await startNeura();
      else if (msg?.type === "openHelp") {
        const doc = await vscode.workspace.openTextDocument({ content: HELP, language: "markdown" });
        await vscode.commands.executeCommand("markdown.showPreview", doc.uri);
      }
    },
    undefined,
    context.subscriptions
  );
}

class NeuraViewProvider implements vscode.WebviewViewProvider {
  constructor(
    private readonly extensionUri: vscode.Uri,
    private readonly context: vscode.ExtensionContext
  ) {}
  private view?: vscode.WebviewView;

  async resolveWebviewView(view: vscode.WebviewView) {
    this.view = view;
    view.webview.options = webviewOptions(this.extensionUri);
    wireMessages(view.webview, this.context);
    view.webview.html = await buildHtml(view.webview, this.extensionUri);
  }

  async reload() {
    if (this.view) this.view.webview.html = await buildHtml(this.view.webview, this.extensionUri);
  }
}

export function activate(context: vscode.ExtensionContext) {
  const provider = new NeuraViewProvider(context.extensionUri, context);
  context.subscriptions.push(
    vscode.window.registerWebviewViewProvider("neura.chat", provider, {
      webviewOptions: { retainContextWhenHidden: true },
    })
  );

  context.subscriptions.push(
    vscode.commands.registerCommand("neura.start", () => startNeura())
  );

  // Open the same UI as a roomy editor tab (better for the graph + trace).
  context.subscriptions.push(
    vscode.commands.registerCommand("neura.openInEditor", async () => {
      const panel = vscode.window.createWebviewPanel(
        "neura.panel",
        "Neura",
        vscode.ViewColumn.Active,
        { ...webviewOptions(context.extensionUri), retainContextWhenHidden: true }
      );
      wireMessages(panel.webview, context);
      panel.webview.html = await buildHtml(panel.webview, context.extensionUri);
    })
  );

  context.subscriptions.push(
    vscode.commands.registerCommand("neura.reload", () => provider.reload())
  );

  // Index the open folder into Neura's knowledge base (semantic file locate).
  context.subscriptions.push(
    vscode.commands.registerCommand("neura.indexWorkspace", async () => {
      const folder = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
      if (!folder) {
        vscode.window.showWarningMessage("Neura: open a folder first.");
        return;
      }
      const base = (vscode.workspace.getConfiguration("neura").get<string>("backendUrl") ||
        "http://127.0.0.1:8010").replace(/\/+$/, "");
      await vscode.window.withProgress(
        { location: vscode.ProgressLocation.Notification, title: `Neura: indexing ${folder}…` },
        async () => {
          try {
            const r = await fetch(`${base}/api/ingest`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ paths: [folder] }),
            });
            if (!r.ok) throw new Error(`${r.status}`);
            vscode.window.showInformationMessage("Neura: folder indexed.");
          } catch (e: any) {
            vscode.window.showErrorMessage(
              `Neura: indexing failed (${e?.message || e}). Is the backend running at ${base}?`
            );
          }
        }
      );
    })
  );
}

export function deactivate() {}
