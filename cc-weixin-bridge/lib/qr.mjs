import QRCode from "qrcode";

/** 跨平台终端渲染二维码（Unicode 方块，Windows/macOS/Linux 通用） */
export async function renderQR(url) {
  const str = await QRCode.toString(url, { type: "terminal", small: true });
  console.log(str);
}
