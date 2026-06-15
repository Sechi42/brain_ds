import { spawn } from "node:child_process";
import { mkdir, mkdtemp, writeFile } from "node:fs/promises";
import net from "node:net";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const REPO_ROOT = path.resolve(__dirname, "..", "..", "..");
const TEMP_ROOT = path.join(os.tmpdir(), "opencode");
const STATE_FILE = path.join(TEMP_ROOT, "brain-ds-live-e2e-state.json");

type LiveState = {
  baseUrl: string;
  mcpBridgeUrl: string;
  sandboxRoot: string;
  uiPid: number;
  mcpBridgePid: number;
};

export default async function globalSetup(): Promise<void> {
  await mkdir(TEMP_ROOT, { recursive: true });

  const sandboxRoot = await mkdtemp(path.join(TEMP_ROOT, "brain-ds-live-"));
  await mkdir(path.join(sandboxRoot, ".brain_ds"), { recursive: true });

  const uiPort = await getFreePort();
  const mcpBridgePort = await getFreePort();

  const uiProcess = spawn("uv", [
    "run",
    "--no-sync",
    "python",
    "-m",
    "brain_ds",
    "ui",
    "serve",
    "--project-root",
    sandboxRoot,
    "--port",
    String(uiPort),
  ], {
    cwd: REPO_ROOT,
    env: { ...process.env, PYTHONUNBUFFERED: "1" },
    stdio: "ignore",
    detached: true,
  });
  uiProcess.unref();

  const bridgeScript = path.resolve(__dirname, "mcp-bridge.mjs");
  const bridgeProcess = spawn(process.execPath, [bridgeScript, "--project-root", sandboxRoot, "--port", String(mcpBridgePort)], {
    cwd: REPO_ROOT,
    env: { ...process.env },
    stdio: "ignore",
    detached: true,
  });
  bridgeProcess.unref();

  const baseUrl = `http://127.0.0.1:${uiPort}`;
  const mcpBridgeUrl = `http://127.0.0.1:${mcpBridgePort}`;

  await waitForUrl(`${baseUrl}/api/graphs`);
  await waitForUrl(`${mcpBridgeUrl}/health`);

  const state: LiveState = {
    baseUrl,
    mcpBridgeUrl,
    sandboxRoot,
    uiPid: uiProcess.pid ?? 0,
    mcpBridgePid: bridgeProcess.pid ?? 0,
  };

  await writeFile(STATE_FILE, JSON.stringify(state, null, 2), "utf8");
  process.env.BRAIN_DS_E2E_BASE_URL = baseUrl;
  process.env.BRAIN_DS_ECOSYSTEM_URL = baseUrl;
  process.env.BRAIN_DS_E2E_MCP_BRIDGE_URL = mcpBridgeUrl;
  process.env.BRAIN_DS_E2E_SANDBOX_ROOT = sandboxRoot;
  process.env.BRAIN_DS_E2E_STATE_FILE = STATE_FILE;
}

async function getFreePort(): Promise<number> {
  return await new Promise<number>((resolve, reject) => {
    const server = net.createServer();
    server.unref();
    server.on("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      if (!address || typeof address === "string") {
        server.close(() => reject(new Error("Could not resolve a free port")));
        return;
      }
      const { port } = address;
      server.close((error) => {
        if (error) reject(error);
        else resolve(port);
      });
    });
  });
}

async function waitForUrl(url: string, timeoutMs = 30_000): Promise<void> {
  const startedAt = Date.now();
  let lastError: unknown = null;
  while (Date.now() - startedAt < timeoutMs) {
    try {
      const response = await fetch(url);
      if (response.ok) return;
      lastError = new Error(`Unexpected status ${response.status} for ${url}`);
    } catch (error) {
      lastError = error;
    }
    await new Promise((resolve) => setTimeout(resolve, 200));
  }
  throw new Error(`Timed out waiting for ${url}: ${String(lastError)}`);
}
