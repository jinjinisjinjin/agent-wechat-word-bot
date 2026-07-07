import { query } from "@anthropic-ai/claude-agent-sdk";
import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { homedir } from "node:os";
import Debug from "debug";

const debug = Debug("cc-weixin:claude");

/** 专用工作区，避免污染项目目录 */
const WORKSPACE = join(homedir(), ".cc-weixin", "workspace");
mkdirSync(WORKSPACE, { recursive: true });

/** 每个微信用户的会话 ID，用于多轮对话 */
const userSessions = new Map();

/** 调用 Claude Code agent，返回最终文本回复 */
export async function askClaude(userText, userId) {
  const existingSessionId = userId ? userSessions.get(userId) : undefined;
  debug("askClaude called: userId=%s, hasSession=%s, sessionId=%s", userId, !!existingSessionId, existingSessionId);

  const options = {
    model: "sonnet",
    baseTools: [{ preset: "default" }],
    deniedTools: ["AskUserQuestion"],
    cwd: WORKSPACE,
    env: process.env,
    abortController: new AbortController(),
  };

  if (existingSessionId) {
    options.resume = existingSessionId;
    debug("resuming session: %s", existingSessionId);
  }

  // resume 时 prompt 直接传字符串即可；新会话用 generator
  const prompt = existingSessionId
    ? userText
    : (async function* () {
        yield {
          type: "user",
          session_id: "",
          parent_tool_use_id: null,
          message: { role: "user", content: userText },
        };
      })();

  let result = "";
  for await (const msg of query({ prompt, options })) {
    debug("msg type=%s subtype=%s session_id=%s", msg.type, msg.subtype, msg.session_id);
    if (msg.type === "result") {
      result = msg.result ?? "";
      if (userId && msg.session_id) {
        userSessions.set(userId, msg.session_id);
        debug("stored session: userId=%s -> sessionId=%s", userId, msg.session_id);
      }
    }
  }
  debug("result length=%d", result.length);
  return result || "（Claude 无回复）";
}
