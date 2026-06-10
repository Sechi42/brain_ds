import { spawnSync } from "node:child_process";
import { readFile, rm, unlink } from "node:fs/promises";
import os from "node:os";
import path from "node:path";

const STATE_FILE = process.env.BRAIN_DS_E2E_STATE_FILE ?? path.join(os.tmpdir(), "opencode", "brain-ds-live-e2e-state.json");

type LiveState = {
  sandboxRoot: string;
  uiPid: number;
  mcpBridgePid: number;
};

export default async function globalTeardown(): Promise<void> {
  let state: LiveState | null = null;
  try {
    state = JSON.parse(await readFile(STATE_FILE, "utf8")) as LiveState;
  } catch {
    return;
  }

  killProcessTree(state.mcpBridgePid);
  killProcessTree(state.uiPid);
  await rm(state.sandboxRoot, { recursive: true, force: true });
  await unlink(STATE_FILE).catch(() => undefined);
}

function killProcessTree(pid: number): void {
  if (!Number.isInteger(pid) || pid <= 0) return;
  spawnSync("taskkill", ["/PID", String(pid), "/T", "/F"], { stdio: "ignore" });
}
