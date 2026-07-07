#!/usr/bin/env node
/**
 * cc-weixin（改造版）
 * 微信 ← iLink Bot API → 本地 Python 机器人（Flask /webhook）
 *
 * 原版桥接 Claude，本版改为把消息转发到本地 Flask 服务的 /webhook，
 * 由我们自己的 Python 机器人生成回复。iLink 登录/长轮询/收发逻辑保持不变。
 *
 * 用法: node cc-weixin.mjs           # 纯 CLI 模式（默认，推荐用于机器人）
 *       node cc-weixin.mjs --login   # 强制重新扫码
 *       node cc-weixin.mjs --tui     # 原版 TUI（已弃用，需 Claude）
 */

import { createRequire } from "node:module";
const require = createRequire(import.meta.url);
try { require("dotenv").config(); } catch {}

const forceLogin = process.argv.includes("--login");
// 默认使用纯 CLI 模式（机器人场景）；仅当显式传 --tui 时才进入原版 TUI
const noTui = !process.argv.includes("--tui");

if (noTui) {
  // ─── 纯 CLI 模式（原有逻辑） ─────────────────────────────────────
  const { loadSession, login } = await import("./lib/auth.mjs");
  const { getUpdates, sendMessage, extractText } = await import("./lib/messaging.mjs");
  const { askWebhook } = await import("./lib/webhook.mjs");

  async function main() {
    let session = forceLogin ? null : loadSession();
    if (session) {
      console.log(`✅ 已连接（Bot: ${session.accountId}）\n`);
    } else {
      session = await login();
    }

    const { token, baseUrl } = session;

    let running = true;
    process.on("SIGINT", () => {
      console.log("\n\n👋 正在退出...");
      running = false;
    });

    console.log("🚀 开始长轮询收消息（Ctrl+C 退出）...\n");
    let buf = "";

    while (running) {
      try {
        const resp = await getUpdates(baseUrl, token, buf);
        if (resp.get_updates_buf) buf = resp.get_updates_buf;

        for (const msg of resp.msgs ?? []) {
          if (msg.message_type !== 1) continue;

          const from = msg.from_user_id;
          const text = extractText(msg);
          const ctx = msg.context_token;

          console.log(`📩 [${new Date().toLocaleTimeString()}] ${from}`);
          console.log(`   ${text}`);

          process.stdout.write("   🤔 机器人处理中...");
          const reply = await askWebhook(text, from);
          process.stdout.write(" 完成\n");

          await sendMessage(baseUrl, token, from, reply, ctx);
          console.log(`   ✅ ${reply.slice(0, 80)}${reply.length > 80 ? "…" : ""}\n`);
        }
      } catch (err) {
        if (err.message?.includes("session timeout") || err.message?.includes("-14")) {
          console.error("❌ Session 已过期，请重新运行: npm start -- --login");
          process.exit(1);
        }
        console.error(`⚠️  轮询出错: ${err.message}，3s 后重试...`);
        await new Promise((r) => setTimeout(r, 3000));
      }
    }

    console.log("✅ 已退出");
  }

  main().catch((err) => {
    console.error("Fatal:", err.message);
    process.exit(1);
  });
} else {
  // ─── TUI 模式 ────────────────────────────────────────────────────
  const { startTUI } = await import("./lib/tui/index.mjs");
  startTUI({ forceLogin });
}
