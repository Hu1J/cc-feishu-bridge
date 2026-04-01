# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

<!-- Add new releases below this line. Maintainer updates before each tag. -->

## [0.1.1] - 2026-04-02

### Added
- **双向图片/文件传输**：用户发送图片或文件给机器人，Claude 可以读取并处理；Claude 生成的图片会自动发回飞书
  - 图片：下载保存至 `.cc-feishu-bridge/received_images/`，以本地路径传给 Claude
  - 文件：下载保存至 `.cc-feishu-bridge/received_files/`，以本地路径传给 Claude
  - Claude 返回的图片：以 base64 接收，上传至飞书后发回聊天

### Fixed
- 修复 `test_integration.py` 中引用不存在方法 `_parse_event` 的问题
- 修复 `test_main_ws.py` 中旧包名 `src.main` 的问题

## [0.1.0] - 2026-04-01

### Added
- 初始版本，支持飞书文字消息收发
- 扫码安装流程
- `/new` 和 `/status` 命令
- bypass 风险提示（首次确认后记录到配置）
- 回复内容记录到日志
