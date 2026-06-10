# PR 违禁关键字检测 GitHub Action — 设计文档

**日期：** 2026-06-10

## 背景与目标

在 GitHub PR 流程中自动扫描新增代码，检测违禁关键字（硬编码密码、API Key、TODO 等），并以 inline review comment 的形式提示开发者，效果类似 GitHub Copilot Code Review。

## 约束条件

- 运行环境：self-hosted runner（容器形式，Python 可用，不支持 DinD）
- 触发时机：PR 创建（opened）和更新（synchronize）
- 检测范围：仅检测 diff 中新增的行（`+` 开头），不检测历史代码
- 部署形式：GitHub Actions composite action，存放于独立仓库，业务仓库通过 `uses` 引用

## 仓库结构

```
keyword-checker/                  # Action 仓库
├── action.yml
├── src/
│   └── check_keywords.py
└── .github/
    └── workflows/
        └── test.yml

业务仓库
├── .github/
│   ├── workflows/
│   │   └── pr-keyword-check.yml
│   └── keywords.yml
```

## 配置文件格式（`.github/keywords.yml`）

```yaml
keywords:
  - type: string
    value: "password"
    message: "疑似硬编码密码，请使用环境变量或密钥管理服务"
  - type: string
    value: "TODO"
    message: "请在合并前解决此 TODO"
  - type: regex
    value: "sk-[a-zA-Z0-9]{32,}"
    message: "疑似 OpenAI API Key 泄露"
  - type: regex
    value: "(?i)secret\\s*=\\s*['\"][^'\"]+['\"]"
    message: "疑似硬编码 secret"
```

字段说明：
- `type`：`string`（精确子串匹配）或 `regex`（Python `re` 正则）
- `value`：关键字或正则表达式
- `message`：触发时写入 inline comment 的提示信息

## 核心检测流程

```
1. 读取 keywords.yml，解析规则列表
2. 调用 GitHub API 获取 PR 变更文件列表及 diff
3. 解析 diff，提取新增行（+ 开头）及其文件名、行号（position）
4. 对每个新增行逐条匹配规则（string 用 in，regex 用 re.search）
5. 同一行命中多条规则时，合并为一条 comment
6. 收集所有命中结果，调用 Pull Request Reviews API 一次性提交
   - 有命中 → status: REQUEST_CHANGES
   - 无命中 → status: COMMENT（可配置为 APPROVE）
```

## Action 定义（`action.yml`）

```yaml
name: 'Keyword Checker'
description: '检测 PR diff 中的违禁关键字并发表 inline review comment'
inputs:
  github-token:
    description: 'GitHub Token，用于调用 API'
    required: true
  keywords-path:
    description: '关键字配置文件路径'
    required: false
    default: '.github/keywords.yml'
  no-violation-action:
    description: '无违规时的行为：approve 或 comment'
    required: false
    default: 'comment'
runs:
  using: 'composite'
  steps:
    - name: Run keyword check
      shell: python3 {0}
      run: ${{ github.action_path }}/src/check_keywords.py
      env:
        GITHUB_TOKEN: ${{ inputs.github-token }}
        KEYWORDS_PATH: ${{ inputs.keywords-path }}
        NO_VIOLATION_ACTION: ${{ inputs.no-violation-action }}
        PR_NUMBER: ${{ github.event.pull_request.number }}
        REPO: ${{ github.repository }}
```

## 业务仓库 Workflow（`pr-keyword-check.yml`）

```yaml
name: PR Keyword Check
on:
  pull_request:
    types: [opened, synchronize]

jobs:
  check:
    runs-on: self-hosted
    steps:
      - uses: actions/checkout@v4
      - uses: your-org/keyword-checker@v1
        with:
          github-token: ${{ secrets.GITHUB_TOKEN }}
```

## GitHub API 调用

| 用途 | API |
|------|-----|
| 获取 PR 变更文件及 diff | `GET /repos/{owner}/{repo}/pulls/{pull_number}/files` |
| 提交 inline comments + review 状态 | `POST /repos/{owner}/{repo}/pulls/{pull_number}/reviews` |

使用一次 review 请求提交所有 comment，与 Copilot Code Review 行为一致，避免多次 API 调用。

## 错误处理

| 场景 | 处理方式 |
|------|---------|
| `keywords.yml` 不存在 | 输出警告，Action 以成功状态退出，不阻断 PR |
| 正则表达式非法 | 跳过该规则，输出警告日志，继续检测其余规则 |
| GitHub API 错误 / 限流 | 抛出异常，Action 失败退出，PR 检查标红 |
| 同一行命中多条规则 | 合并为一条 comment，列出所有提示信息 |
| PR diff 超过 300 个文件 | 在 PR 发汇总 comment，说明已跳过的文件 |

## 测试策略

Action 仓库自带单元测试，覆盖以下场景：

- 字符串精确匹配命中
- 正则匹配命中
- 同一行多条规则命中（合并 comment）
- 无命中（正常通过）
- 非法正则（跳过 + 警告）
- `keywords.yml` 缺失（警告 + 成功退出）
