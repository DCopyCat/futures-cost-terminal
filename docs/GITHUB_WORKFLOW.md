# GitHub 托管与版本更新（推荐：私有仓库）

## 一次性准备

1. 在 GitHub 建立 **Private** 仓库：建议名 `futures-cost-terminal`，不要勾选自动创建 README（已有）。
2. 安装 Git（Windows），把本项目解压到固定文件夹。
3. 在项目文件夹打开 PowerShell 或 Git Bash，执行：

```bash
git init -b main
git add .
git commit -m "chore: import Futures Cost Terminal v0.5.0"
git tag v0.5.0
git remote add origin https://github.com/<你的用户名>/futures-cost-terminal.git
git push -u origin main
git push origin v0.5.0
```

`<你的用户名>` 替换为你自己的 GitHub 用户名。首次推送可能需要 GitHub 的网页登录/凭据管理器授权，不要将密码或 Token 发给聊天。

如果使用 ChatGPT 的 GitHub 连接，授权后可以让我在对应仓库按你的新需求提出改动、检查差异及组织版本提交；实际写入操作以连接权限和相应确认流程为准。

## 日常更新策略

- `main`：保持最近验证过的稳定版。
- 新功能/修复：单独分支（如 `feat/dce-margin` 或 `fix/cne-empty-report`），跑离线测试，经过检查再合并。
- 正式发布：提交 CHANGELOG、修改 VERSION、生成 Git tag（如 `v0.5.1` 或 `v0.6.0`）。
- 回滚：在 GitHub 查看历史提交或 Releases，按需检出历史 tag。

## 数据安全

- 推荐 **Private**，因为仓库中仍有公司默认费率 CSV（来源 PDF）及其历史版本。
- `data/company_overrides.csv`、`data/exchange_overrides.csv` 仅本地保存；首次启动会自动从空模板创建。
- `cn_equity_lake/`、`reports/`、`logs/`、`.env`、`.streamlit/secrets.toml`、API Token、客户身份、结算单一律不要提交。
- GitHub 存源码与版本，不是自动托管/运行本地 Streamlit 程序。要随时在网上打开界面，需要另外部署，并审查授权与数据隐私。
- GitHub Actions 当前仅运行模拟/离线回归测试，不代表最新交易日 API 成功获取数据。
