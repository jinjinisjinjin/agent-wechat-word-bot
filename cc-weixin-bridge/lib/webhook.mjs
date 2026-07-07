/**
 * webhook.mjs — 将微信消息转发到本地 Python 机器人（Flask /webhook）
 *
 * 这是对本仓库的改造点：原版在此调用 Claude Code Agent，
 * 这里改为把消息 POST 到本地 Flask 服务的 /webhook，
 * 由我们自己的 Python 机器人（main.py / message_handler）生成回复。
 * 其余 iLink 登录、长轮询、收发逻辑全部复用原版。
 */
/**
 * 调用本地机器人的 webhook，返回回复文本。
 * @param {string} text 微信消息文本
 * @param {string} from 发送者 user_id
 * @returns {Promise<string>}
 */
export async function askWebhook(text, from) {
  const url = process.env.WEBHOOK_URL || "http://localhost:9090/webhook";
  try {
    const resp = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, from }),
    });
    if (!resp.ok) {
      const text = await resp.text().catch(() => "");
      console.error(`⚠️ webhook 返回 HTTP ${resp.status}: ${text.slice(0, 200)}`);
      return "（机器人服务异常，请稍后再试）";
    }
    const data = await resp.json();
    return data.reply || "（机器人无回复）";
  } catch (e) {
    console.error("❌ webhook 调用失败:", e.message);
    return "（机器人暂时无法连接，请稍后再试）";
  }
}
