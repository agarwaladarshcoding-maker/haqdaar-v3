import { DOOR } from "../../../lib/api";

// The browser never talks to the data door itself. It asks here, and this relays the few
// requests the pages need, with the header the door wants for anything that acts.
const GET_OK = [/^live$/, /^calls\/[\w.~-]+$/];
const POST_OK = [/^call-me$/, /^test-call$/, /^test-call\/input$/];

async function relay(request: Request, path: string[], allowed: RegExp[]): Promise<Response> {
  const target = path.join("/");
  if (!allowed.some((rule) => rule.test(target))) return Response.json({ detail: "Not found." }, { status: 404 });
  try {
    const r = await fetch(`${DOOR}/api/${target}`, {
      method: request.method,
      headers: { "content-type": "application/json", "x-haqdaar": "dashboard" },
      body: request.method === "POST" ? (await request.text()) || "{}" : undefined,
      cache: "no-store",
      signal: AbortSignal.timeout(8000),
    });
    return new Response(await r.text(), { status: r.status, headers: { "content-type": "application/json" } });
  } catch {
    return Response.json({ detail: "The data door is not answering. Start it with: make dashboard" }, { status: 502 });
  }
}

type Ctx = { params: Promise<{ path: string[] }> };

export async function GET(request: Request, { params }: Ctx) {
  return relay(request, (await params).path, GET_OK);
}

export async function POST(request: Request, { params }: Ctx) {
  // Only this site's own pages may ask for an action.
  const origin = request.headers.get("origin");
  if (origin && new URL(origin).host !== request.headers.get("host")) {
    return Response.json({ detail: "Not allowed." }, { status: 403 });
  }
  return relay(request, (await params).path, POST_OK);
}
