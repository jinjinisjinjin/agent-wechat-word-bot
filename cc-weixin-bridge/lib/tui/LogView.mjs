import React from "react";
import { Text, Box } from "ink";

const h = React.createElement;

let logId = 0;

export function makeLog(type, text, from) {
  return {
    id: ++logId,
    time: new Date().toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" }),
    type,
    text,
    from,
  };
}

/** 在框内渲染最近 maxLines 条日志，不足的用空行填充 */
export function LogView({ logs, maxLines = 12 }) {
  const visible = logs.slice(-maxLines);
  const padCount = Math.max(0, maxLines - visible.length);

  return h(Box, { flexDirection: "column", paddingX: 1 },
    ...visible.map((log) =>
      h(Text, { key: log.id, wrap: "truncate" },
        h(Text, { dimColor: true }, log.time),
        " ",
        log.type === "in" ? h(Text, { color: "cyan" }, "📩 ", log.from, ": ", log.text) : null,
        log.type === "out" ? h(Text, { color: "green" }, "✅ → ", log.text) : null,
        log.type === "info" ? h(Text, { color: "yellow" }, log.text) : null,
        log.type === "error" ? h(Text, { color: "red" }, "❌ ", log.text) : null,
        log.type === "thinking" ? h(Text, { color: "gray" }, "🤔 ", log.text) : null,
      ),
    ),
    ...Array.from({ length: padCount }, (_, i) =>
      h(Text, { key: `pad-${i}` }, " "),
    ),
  );
}
