---
name: github-keychain-upload
description: 无需用户重新登录，从 macOS 钥匙串读取已有的 GitHub token，调用 GitHub Contents API 把任意本地文件上传/更新到指定仓库。触发场景：用户要"上传到我的 GitHub""把文件提交到 GitHub 仓库""push 一个文件到 repo"，且本机已用 git/gh 登录过 GitHub（凭据在钥匙串）。涵盖首次创建、更新已有文件（带 SHA）、纯标准库实现、token 安全注意事项。
agent_created: true
---

# 从 macOS 钥匙串取 token + GitHub Contents API 上传文件

## Purpose
把本地文件直接 PUT 进用户的 GitHub 仓库（指定分支），全程**不需要用户重新登录或提供密码**——token 从本机钥匙串里已有的 git/gh 凭据读取。适合"帮我把这个文件传到我 GitHub 上"这类需求。

## 关键约束 / 避坑（动手前必读）
1. **Token 来自本机钥匙串，不是凭空生成。** 依赖用户这台 Mac 之前用 `git push` 或 `gh auth login` 登录过 GitHub，凭据存进了 macOS 钥匙串（git-credential-osxkeychain）。读取命令：
   ```python
   import subprocess
   out = subprocess.run(['git', 'credential', 'fill'],
                       input='protocol=https\nhost=github.com\n\n',
                       capture_output=True, text=True).stdout
   token = None
   for line in out.splitlines():
       if line.startswith('password='):
           token = line[len('password='):].strip()
   ```
   若 `token is None`，说明本机没登录过 GitHub → 让用户先 `gh auth login` 或 `git clone` 一次。跨电脑不适用（那台得自己登录）。
2. **API 端点**：`PUT https://api.github.com/repos/{owner}/{repo}/contents/{path}`。
   - 路径 `{path}` 要 `urllib.parse.quote()` 编码（中文/空格必编码，否则 404）。
   - Header：`Authorization: Bearer {token}`、`Accept: application/vnd.github+json`、`User-Agent` 任意非空。
3. **body 必须是 JSON**，且 `content` 是**文件内容的 base64**（不是原文）：
   ```python
   import base64, json
   b64 = base64.b64encode(open(local, 'rb').read()).decode()
   data = json.dumps({'message': '提交说明', 'content': b64, 'branch': 'main'}).encode()
   ```
4. **⚠️ 更新已有文件必须带 `sha`，否则报 422。** 首次创建（文件不存在）**不带** sha；若文件已存在要覆盖，先 `GET` 同端点拿到 `sha` 字段，再在 body 加 `"sha": "<原sha>"`。判断方法：先尝试 PUT，若返回 422 且提示 "sha" 缺失，则 GET 取 sha 重试。
5. **纯标准库实现，零依赖。** 用 `urllib.request`（不是 `requests`），避免环境装包问题。完整示例：
   ```python
   import subprocess, base64, json, urllib.request, urllib.parse, sys

   # 1) 取 token
   out = subprocess.run(['git', 'credential', 'fill'],
                       input='protocol=https\nhost=github.com\n\n',
                       capture_output=True, text=True).stdout
   token = next((l[len('password='):].strip() for l in out.splitlines()
                 if l.startswith('password=')), None)
   if not token:
       print('NO_TOKEN'); sys.exit(1)

   # 2) 读文件 + base64
   repo = 'OWNER/REPO'
   local = '/path/to/local/file.md'
   fname = urllib.parse.quote('file.md')
   url = f'https://api.github.com/repos/{repo}/contents/{fname}'
   b64 = base64.b64encode(open(local, 'rb').read()).decode()

   # 3) 先看是否已存在（拿 sha，用于更新）
   req = urllib.request.Request(url, headers={
       'Authorization': f'Bearer {token}', 'Accept': 'application/vnd.github+json',
       'User-Agent': 'workbuddy'})
   sha = None
   try:
       sha = json.load(urllib.request.urlopen(req)).get('sha')
   except urllib.error.HTTPError as e:
       if e.code != 404:
           raise

   # 4) PUT
   body = {'message': 'docs: 上传文件', 'content': b64, 'branch': 'main'}
   if sha:
       body['sha'] = sha
   req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                method='PUT', headers={
           'Authorization': f'Bearer {token}',
           'Accept': 'application/vnd.github+json',
           'User-Agent': 'workbuddy'})
   try:
       resp = urllib.request.urlopen(req)
       j = json.load(resp)
       print('OK', resp.status, j['content']['html_url'])
   except urllib.error.HTTPError as e:
       print('ERR', e.code, e.read().decode()[:600]); sys.exit(1)
   ```
6. **返回码含义**：`201 Created`（新建成功）、`200 OK`（更新成功）、`422`（缺 sha / 内容空 / 分支不存在）、`401`（token 失效或无权限）、`404`（仓库/路径不对，常因未 quote 编码）。
7. **🔒 安全铁律**：token 只在运行时从钥匙串读取，**绝不写入文件、聊天、记忆、日志**。`print` 只输出返回的 `html_url`（文件链接），不打印 token。其他 AI 在本机跑同样逻辑也能拿到 token，但换电脑无效。

## Workflow
1. 确认本机登录过 GitHub（钥匙串有凭据）；否则让用户先 `gh auth login`。
2. 确定 `repo=OWNER/REPO`、`local` 本地路径、`fname` 仓库内路径（中文需 quote）。
3. 用上面脚本读取 token → base64 → 先 GET 探测 sha → PUT 上传（有 sha 则更新，无则创建）。
4. 返回 `html_url` 给用户作为结果链接。

## 适用 / 不适用
- ✅ 单个或少量文件提交到公开/私有仓库（有 token 权限即可）。
- ❌ 大批量/二进制大文件（>100MB 用 Git LFS，本 API 不支持）。
- ❌ 需要复杂 git 历史/多文件原子提交（用 `git` 命令行更合适）。
