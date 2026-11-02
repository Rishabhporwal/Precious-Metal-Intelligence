import { NextResponse } from "next/server";

export async function GET() {
  return NextResponse.json({
    status: "ok",
    service: "pmi-web",
    version: "0.1.0",
    uptimeSec: Math.round(process.uptime()),
    timestamp: new Date().toISOString(),
  });
}
