# 不用密码，把文件上传到 GitHub 仓库的方法

> 适用场景：你本机已经用 `git` 或 `gh` 登录过 GitHub（凭据存在 macOS 钥匙串里），想让 AI 或脚本直接把某个本地文件传进你的仓库，**全程不需要你再输入账号密码**。

## 核心思路

1. 从 macOS 钥匙串读取已有的 GitHub token（通过 `git credential fill` 命令，git 自带的 osxkeychain 助手会去钥匙串查）。
2. 用这个 token 调用 GitHub 官方的 **Contents API**，把文件内容以 base64 编码后 `PUT` 进指定仓库的指定路径。
3. 返回 `201` 表示新建成功，`200` 表示更新成功。

## 第一步：取 token（关键）

不需要用户给密码。在 Mac 上运行：

```python
import subprocess
out = subprocess.run(['git', 'credential', 'fill'],
                    input='protocol=https\nhost=github.com\n\n',
                    capture_output=True, text=True).stdout
token = None
for line in out.splitlines():
    if line.startswith('password='):
        token = line[len('password='):].strip()
# token 即 GitHub Personal Access Token，来自本机钥匙串
```

如果取不到（返回空），说明这台电脑从没登录过 GitHub → 先让用户执行 `gh auth login` 或 `git clone` 一次。

> 注意：这个方法依赖**本机钥匙串**。换一台没登录过的电脑就失效了。

## 第二步：调用 GitHub Contents API 上传

```python
import base64, json, urllib.request, urllib.parse

repo = '你的用户名/你的仓库'          # 例如 jinjinisjinjin/agent-wechat-word-bot
local = '/本地/文件/路径.md'          # 要上传的本地文件
fname = urllib.parse.quote('仓库内路径.md')  # 中文/空格必须用 quote 编码
url = f'https://api.github.com/repos/{repo}/contents/{fname}'

# 文件内容 base64 编码
b64 = base64.b64encode(open(local, 'rb').read()).decode()

# 先探测文件是否已存在（拿到 sha，用于覆盖更新）
req = urllib.request.Request(url, headers={
    'Authorization': f'Bearer {token}',
    'Accept': 'application/vnd.github+json',
    'User-Agent': 'uploader'})
sha = None
try:
    sha = json.load(urllib.request.urlopen(req)).get('sha')
except urllib.error.HTTPError as e:
    if e.code != 404:
        raise

# 组装请求体
body = {'message': '上传文件', 'content': b64, 'branch': 'main'}
if sha:
    body['sha'] = sha   # ⚠️ 覆盖已有文件必须带 sha，否则报 422

req = urllib.request.Request(url, data=json.dumps(body).encode(),
                             method='PUT', headers={
    'Authorization': f'Bearer {token}',
    'Accept': 'application/vnd.github+json',
    'User-Agent': 'uploader'})
resp = urllib.request.urlopen(req)
print('OK', resp.status, json.load(resp)['content']['html_url'])
```

## 三个最容易踩的坑

| 坑 | 现象 | 解决 |
|----|------|------|
| **更新文件不带 `sha`** | 报 `422`，提示 sha 缺失 | 先 GET 拿 sha，再 PUT 时放进 body |
| **路径没编码** | 报 `404` | `fname` 用 `urllib.parse.quote()` 处理（中文/空格必编码） |
| **token 取不到** | 报 `401` | 本机先 `gh auth login` 或 `git` 登录过 GitHub |

## 安全提醒

- token 只在运行时从钥匙串读取，**不要写进文件、聊天记录、记忆或日志**。
- 脚本只输出返回的 `html_url`（文件链接），绝不打印 token 本身。
- 这套方法通用：改 `repo`、`local`、`fname` 三个变量，就能往任意有权限的仓库传任意文件。

## 返回码速查

- `201 Created` → 新建成功
- `200 OK` → 更新成功
- `422` → 缺 sha / 内容为空 / 分支不存在
- `401` → token 失效或无权限
- `404` → 仓库或路径不对（常因未编码）
