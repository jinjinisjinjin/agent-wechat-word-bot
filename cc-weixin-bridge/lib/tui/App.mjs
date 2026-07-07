import React, { useState, useEffect, useRef, useCallback } from "react";
import { Text, Box } from "ink";
import { Header } from "./Header.mjs";
import { LogView, makeLog } from "./LogView.mjs";
import { Menu } from "./Menu.mjs";
import { loadSession, login, clearSession } from "../auth.mjs";
import { getUpdates, sendMessage, extractText } from "../messaging.mjs";
import { askClaude } from "../claude.mjs";

const h = React.createElement;

export function App({ forceLogin }) {
  const [status, setStatus] = useState("connecting");
  const [accountId, setAccountId] = useState("");
  const [logs, setLogs] = useState([]);
  const [qrText, setQrText] = useState(null);
  const [startTime] = useState(Date.now());
  const [menuDisabled, setMenuDisabled] = useState(false);

  const sessionRef = useRef(null);
  const runningRef = useRef(true);
  const bufRef = useRef("");

  const addLog = useCallback((type, text, from) => {
    setLogs((prev) => [...prev, makeLog(type, text, from)]);
  }, []);

  // Login + message loop
  useEffect(() => {
    let cancelled = false;

    async function start() {
      // Login
      try {
        let session = forceLogin ? null : loadSession();
        if (session) {
          sessionRef.current = session;
          setAccountId(session.accountId);
          setStatus("connected");
          addLog("info", `已连接 Bot: ${session.accountId}`);
        } else {
          setStatus("connecting");
          addLog("info", "开始微信扫码登录...");

          session = await login({
            onQR: (qrString) => setQrText(qrString),
            onStatus: (msg) => addLog("info", msg),
          });

          setQrText(null);
          sessionRef.current = session;
          setAccountId(session.accountId);
          setStatus("connected");
          addLog("info", `登录成功！Bot: ${session.accountId}`);
        }
      } catch (err) {
        addLog("error", `登录失败: ${err.message}`);
        setStatus("disconnected");
        return;
      }

      // Message loop
      bufRef.current = "";
      addLog("info", "开始接收消息...");

      while (runningRef.current && !cancelled) {
        try {
          const { token, baseUrl } = sessionRef.current;
          const resp = await getUpdates(baseUrl, token, bufRef.current);
          if (resp.get_updates_buf) bufRef.current = resp.get_updates_buf;

          for (const msg of resp.msgs ?? []) {
            if (msg.message_type !== 1) continue;

            const from = msg.from_user_id;
            const text = extractText(msg);
            const ctx = msg.context_token;

            addLog("in", text, from);
            addLog("thinking", "Claude 思考中...");

            const reply = await askClaude(text, from);
            await sendMessage(baseUrl, token, from, reply, ctx);

            addLog("out", reply.slice(0, 200) + (reply.length > 200 ? "…" : ""));
          }
        } catch (err) {
          if (err.message?.includes("session timeout") || err.message?.includes("-14")) {
            addLog("error", "Session 已过期，请按 L 重新登录");
            setStatus("disconnected");
            return;
          }
          addLog("error", `轮询出错: ${err.message}，3s 后重试...`);
          await new Promise((r) => setTimeout(r, 3000));
        }
      }
    }

    start();
    return () => { cancelled = true; };
  }, [forceLogin, addLog]);

  const handleLogout = useCallback(() => {
    setMenuDisabled(true);
    runningRef.current = false;
    addLog("info", "正在退出登录...");
    clearSession();
    setStatus("disconnected");
    setAccountId("");
    addLog("info", "已清除登录信息，请重新启动以扫码登录");
    setTimeout(() => process.exit(0), 500);
  }, [addLog]);

  const handleReconnect = useCallback(() => {
    setMenuDisabled(true);
    runningRef.current = false;
    addLog("info", "正在重连...");
    setTimeout(() => process.exit(100), 300); // Exit 100 signals reconnect
  }, [addLog]);

  const handleQuit = useCallback(() => {
    runningRef.current = false;
    addLog("info", "正在退出...");
    setTimeout(() => process.exit(0), 200);
  }, [addLog]);

  return h(Box, { flexDirection: "column", width: "100%" },
    h(Header, { accountId, status, startTime }),
    h(Box, { borderStyle: "single", borderTop: false, borderBottom: false, flexDirection: "column" },
      qrText
        ? h(Box, { flexDirection: "column", paddingX: 1 },
            h(Text, { bold: true, color: "yellow" }, "📱 请用微信扫描以下二维码："),
            h(Text, null, qrText),
          )
        : h(LogView, { logs }),
    ),
    h(Menu, {
      onLogout: handleLogout,
      onReconnect: handleReconnect,
      onQuit: handleQuit,
      disabled: menuDisabled,
    }),
  );
}
