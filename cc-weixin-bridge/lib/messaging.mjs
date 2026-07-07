import crypto from "node:crypto";
import { apiPost } from "./api.mjs";

/** 长轮询获取新消息 */
export async function getUpdates(baseUrl, token, getUpdatesBuf) {
  const resp = await apiPost(
    baseUrl,
    "ilink/bot/getupdates",
    { get_updates_buf: getUpdatesBuf ?? "" },
    token,
    38_000,
  );
  return resp ?? { ret: 0, msgs: [], get_updates_buf: getUpdatesBuf };
}

/** 发送文本消息 */
export async function sendMessage(baseUrl, token, toUserId, text, contextToken) {
  const clientId = `wcb-${crypto.randomUUID()}`;
  await apiPost(
    baseUrl,
    "ilink/bot/sendmessage",
    {
      msg: {
        from_user_id: "",
        to_user_id: toUserId,
        client_id: clientId,
        message_type: 2,
        message_state: 2,
        context_token: contextToken,
        item_list: [{ type: 1, text_item: { text } }],
      },
    },
    token,
  );
  return clientId;
}

/** 从消息 item_list 提取纯文本 */
export function extractText(msg) {
  for (const item of msg.item_list ?? []) {
    if (item.type === 1 && item.text_item?.text) return item.text_item.text;
    if (item.type === 3 && item.voice_item?.text) return `[语音] ${item.voice_item.text}`;
    if (item.type === 2) return "[图片]";
    if (item.type === 4) return `[文件] ${item.file_item?.file_name ?? ""}`;
    if (item.type === 5) return "[视频]";
  }
  return "[空消息]";
}
