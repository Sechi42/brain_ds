import http from "node:http";
import { spawn } from "node:child_process";
import { createInterface } from "node:readline";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const REPO_ROOT = path.resolve(__dirname, "..", "..", "..");

const args = process.argv.slice(2);
const projectRoot = getArgValue(args, "--project-root");
const port = Number(getArgValue(args, "--port"));

if (!projectRoot || !Number.isFinite(port)) {
  throw new Error("Usage: node mcp-bridge.mjs --project-root <path> --port <port>");
}

const mcpProcess = spawn("uv", [
  "run",
  "--no-sync",
  "python",
  "-m",
  "brain_ds",
  "mcp",
  "--project-root",
  projectRoot,
], {
  cwd: REPO_ROOT,
  env: { ...process.env, PYTHONUNBUFFERED: "1" },
  stdio: ["pipe", "pipe", "pipe"],
});

let nextId = 1;
let queue = Promise.resolve();
let stderrBuffer = "";
const pending = new Map();

const stdoutLines = createInterface({ input: mcpProcess.stdout });
stdoutLines.on("line", (line) => {
  if (!line.trim()) return;
  let payload;
  try {
    payload = JSON.parse(line);
  } catch (error) {
    return;
  }
  const resolver = pending.get(payload.id);
  if (!resolver) return;
  pending.delete(payload.id);
  resolver(payload);
});

mcpProcess.stderr.on("data", (chunk) => {
  stderrBuffer = `${stderrBuffer}${String(chunk)}`.slice(-4000);
});

mcpProcess.on("exit", (code) => {
  for (const [id, resolver] of pending.entries()) {
    pending.delete(id);
    resolver({ error: { code: -32000, message: `MCP exited with code ${code}` } });
  }
});

await initialize();

const server = http.createServer(async (req, res) => {
  if (req.method === "GET" && req.url === "/health") {
    respondJson(res, 200, { ok: true });
    return;
  }

  if (req.method === "POST" && req.url === "/tool") {
    try {
      const body = await readJsonBody(req);
      const result = await enqueueToolCall(body.name, body.arguments ?? {});
      if (result.error) {
        respondJson(res, 500, { error: result.error, stderr: stderrBuffer });
        return;
      }
      respondJson(res, 200, { result: parseToolResult(result) });
      return;
    } catch (error) {
      respondJson(res, 500, { error: String(error), stderr: stderrBuffer });
      return;
    }
  }

  respondJson(res, 404, { error: "Not found" });
});

server.listen(port, "127.0.0.1");

const shutdown = () => {
  server.close(() => {
    if (!mcpProcess.killed) {
      mcpProcess.kill();
    }
    process.exit(0);
  });
};

process.on("SIGTERM", shutdown);
process.on("SIGINT", shutdown);

async function initialize() {
  const response = await sendRpcRequest("initialize", {
    protocolVersion: "2024-11-05",
    capabilities: {},
    clientInfo: { name: "playwright-mcp-bridge", version: "1.0.0" },
  });
  if (response.error) {
    throw new Error(`Failed to initialize MCP bridge: ${JSON.stringify(response.error)}`);
  }
}

function enqueueToolCall(name, args) {
  const run = () => sendRpcRequest("tools/call", { name, arguments: args });
  const next = queue.then(run, run);
  queue = next.then(() => undefined, () => undefined);
  return next;
}

function sendRpcRequest(method, params) {
  const id = nextId;
  nextId += 1;
  const payload = { jsonrpc: "2.0", id, method, params };
  return new Promise((resolve, reject) => {
    const timeoutId = setTimeout(() => {
      pending.delete(id);
      reject(new Error(`Timed out waiting for MCP response to ${method}`));
    }, 10_000);

    pending.set(id, (response) => {
      clearTimeout(timeoutId);
      resolve(response);
    });

    mcpProcess.stdin.write(`${JSON.stringify(payload)}\n`, (error) => {
      if (!error) return;
      clearTimeout(timeoutId);
      pending.delete(id);
      reject(error);
    });
  });
}

async function readJsonBody(req) {
  const chunks = [];
  for await (const chunk of req) {
    chunks.push(Buffer.from(chunk));
  }
  return JSON.parse(Buffer.concat(chunks).toString("utf8") || "{}");
}

function parseToolResult(payload) {
  const text = payload?.result?.content?.[0]?.text;
  return typeof text === "string" ? JSON.parse(text) : null;
}

function respondJson(res, status, body) {
  const json = JSON.stringify(body);
  res.writeHead(status, {
    "content-type": "application/json; charset=utf-8",
    "content-length": Buffer.byteLength(json),
  });
  res.end(json);
}

function getArgValue(argv, flag) {
  const index = argv.indexOf(flag);
  if (index === -1) return "";
  return argv[index + 1] ?? "";
}
