import React from "react";
import { Text, Box, useInput, useStdin } from "ink";

const h = React.createElement;

export function Menu({ onLogout, onReconnect, onQuit, disabled }) {
  const { isRawModeSupported } = useStdin();

  useInput((input) => {
    if (disabled) return;
    if (input === "l" || input === "L") onLogout();
    if (input === "r" || input === "R") onReconnect();
    if (input === "q" || input === "Q") onQuit();
  }, { isActive: isRawModeSupported && !disabled });

  return h(Box, { borderStyle: "single", borderTop: false, paddingX: 1, gap: 2 },
    h(Text, { bold: !disabled, dimColor: disabled }, "[L]ogout"),
    h(Text, { bold: !disabled, dimColor: disabled }, "[R]econnect"),
    h(Text, { bold: !disabled, dimColor: disabled }, "[Q]uit"),
  );
}
