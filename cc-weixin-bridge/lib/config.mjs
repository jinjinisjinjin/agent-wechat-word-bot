import { homedir } from "node:os";
import { join } from "node:path";

export const DEFAULT_BASE_URL = "https://ilinkai.weixin.qq.com";
export const BOT_TYPE = "3";
export const CHANNEL_VERSION = "1.0.2";

export const DATA_DIR = join(homedir(), ".cc-weixin");
export const TOKEN_FILE = join(DATA_DIR, "token.json");
