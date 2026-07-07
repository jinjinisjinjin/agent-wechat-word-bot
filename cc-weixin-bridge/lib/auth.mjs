import fs from "node:fs";
import QRCode from "qrcode";
import { apiGet } from "./api.mjs";
import { renderQR } from "./qr.mjs";
import { DEFAULT_BASE_URL, BOT_TYPE, TOKEN_FILE, DATA_DIR } from "./config.mjs";

/** 加载已保存的 token，无则返回 null */
export function loadSession() {
  if (!fs.existsSync(TOKEN_FILE)) return null;
  return JSON.parse(fs.readFileSync(TOKEN_FILE, "utf-8"));
}

/** 保存 token 到本地文件 */
function saveSession(tokenData) {
  fs.mkdirSync(DATA_DIR, { recursive: true });
  fs.writeFileSync(TOKEN_FILE, JSON.stringify(tokenData, null, 2), "utf-8");
  try { fs.chmodSync(TOKEN_FILE, 0o600); } catch {}
}

/** 清除已保存的 session */
export function clearSession() {
  try { fs.unlinkSync(TOKEN_FILE); } catch {}
}

/**
 * 微信扫码登录完整流程：获取 QR → 渲染 → 轮询 → 返回 session
 *
 * @param {object} [opts] - 可选回调（TUI 模式使用）
 * @param {(qrString: string) => void} [opts.onQR] - QR 码文本回调
 * @param {(msg: string) => void} [opts.onStatus] - 状态消息回调
 */
export async function login(opts) {
  const onQR = opts?.onQR;
  const onStatus = opts?.onStatus;
  const log = onStatus || ((msg) => console.log(msg));

  log("🔐 开始微信扫码登录...");

  const qrResp = await apiGet(DEFAULT_BASE_URL, `ilink/bot/get_bot_qrcode?bot_type=${BOT_TYPE}`);
  let currentQrcode = qrResp.qrcode;

  log("📱 请用微信扫描以下二维码：");

  if (onQR) {
    const qrString = await QRCode.toString(qrResp.qrcode_img_content, { type: "utf8", small: true });
    onQR(qrString);
  } else {
    await renderQR(qrResp.qrcode_img_content);
  }

  log("⏳ 等待扫码...");
  const deadline = Date.now() + 5 * 60_000;
  let refreshCount = 0;

  while (Date.now() < deadline) {
    const status = await apiGet(
      DEFAULT_BASE_URL,
      `ilink/bot/get_qrcode_status?qrcode=${encodeURIComponent(currentQrcode)}`,
    );

    switch (status.status) {
      case "wait":
        if (!onStatus) process.stdout.write(".");
        break;
      case "scaned":
        log("👀 已扫码，请在微信端确认...");
        break;
      case "expired": {
        if (++refreshCount > 3) throw new Error("二维码多次过期，请重新运行");
        log(`⏳ 二维码过期，刷新中 (${refreshCount}/3)...`);
        const newQr = await apiGet(DEFAULT_BASE_URL, `ilink/bot/get_bot_qrcode?bot_type=${BOT_TYPE}`);
        currentQrcode = newQr.qrcode;
        if (onQR) {
          const qrString = await QRCode.toString(newQr.qrcode_img_content, { type: "utf8", small: true });
          onQR(qrString);
        } else {
          await renderQR(newQr.qrcode_img_content);
        }
        break;
      }
      case "confirmed": {
        log("✅ 登录成功！");
        const session = {
          token: status.bot_token,
          baseUrl: status.baseurl || DEFAULT_BASE_URL,
          accountId: status.ilink_bot_id,
          userId: status.ilink_user_id,
          savedAt: new Date().toISOString(),
        };
        saveSession(session);
        log(`Bot ID: ${session.accountId}`);
        return session;
      }
    }

    await new Promise((r) => setTimeout(r, 1000));
  }

  throw new Error("登录超时");
}
