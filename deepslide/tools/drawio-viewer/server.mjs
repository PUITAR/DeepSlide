import fs from "node:fs/promises"
import path from "node:path"
import { fileURLToPath } from "node:url"
import { startHttpServer } from "@next-ai-drawio/mcp-server/dist/http-server.js"

const port = parseInt(process.env.DRAWIO_VIEWER_PORT || process.env.PORT || "6002", 10)
const actualPort = await startHttpServer(port)

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const rootDir = path.resolve(__dirname, "..", "..")
const portFile =
  process.env.DRAWIO_VIEWER_PORT_FILE || path.join(rootDir, ".drawio_viewer_port")
await fs.writeFile(portFile, String(actualPort), "utf8")

setInterval(() => {}, 1 << 30)
