import React from "react";
import { Text, Box } from "ink";

const h = React.createElement;

export function Header({ accountId, status, startTime }) {
  const statusIcon = status === "connected" ? "🟢" : status === "connecting" ? "🟡" : "🔴";
  const statusText = status === "connected" ? "Connected" : status === "connecting" ? "Connecting" : "Disconnected";

  const elapsed = startTime ? formatElapsed(Date.now() - startTime) : "--";

  return h(Box, { borderStyle: "single", borderBottom: false, paddingX: 1, justifyContent: "space-between" },
    h(Text, { bold: true }, "🤖 cc-weixin"),
    h(Text, null, "Bot: ", accountId || "---"),
    h(Text, null, statusIcon, " ", statusText),
    h(Text, { dimColor: true }, elapsed),
  );
}

function formatElapsed(ms) {
  const s = Math.floor(ms / 1000);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  return `${h}h${m % 60}m`;
}
