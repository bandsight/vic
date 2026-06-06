import { createServer } from "node:http";
import { existsSync, readFileSync, statSync } from "node:fs";
import { extname, join, normalize, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(fileURLToPath(new URL("../../", import.meta.url)));
const port = Number.parseInt(process.env.PORT || "8777", 10);

const contentTypes = new Map([
  [".css", "text/css; charset=utf-8"],
  [".geojson", "application/geo+json; charset=utf-8"],
  [".html", "text/html; charset=utf-8"],
  [".js", "text/javascript; charset=utf-8"],
  [".json", "application/json; charset=utf-8"],
  [".svg", "image/svg+xml"],
]);

function resolveRequestPath(requestUrl) {
  const parsed = new URL(requestUrl, `http://127.0.0.1:${port}`);
  const decoded = decodeURIComponent(parsed.pathname);
  const relativePath = decoded.endsWith("/") ? `${decoded.slice(1)}index.html` : decoded.slice(1);
  const filePath = normalize(join(root, relativePath));
  if (!filePath.startsWith(root)) return null;
  return filePath;
}

const server = createServer((request, response) => {
  const filePath = resolveRequestPath(request.url || "/");
  if (!filePath || !existsSync(filePath) || !statSync(filePath).isFile()) {
    response.writeHead(404, { "Content-Type": "text/plain; charset=utf-8" });
    response.end("Not found");
    return;
  }

  const body = readFileSync(filePath);
  response.writeHead(200, {
    "Cache-Control": "no-store",
    "Content-Length": body.length,
    "Content-Type": contentTypes.get(extname(filePath).toLowerCase()) || "application/octet-stream",
  });
  response.end(body);
});

server.listen(port, "127.0.0.1", () => {
  console.log(`Victorian council careers proof running at http://127.0.0.1:${port}/apps/vic-council-job-board/`);
});
