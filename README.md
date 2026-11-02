# CleanShot X / CleanShotX for Mac 下载与历史版本

[中文](#中文) | [English](#english)

## 中文

**CleanShot X（CleanShotX / CleanShot for Mac）** 是 macOS 截图与屏幕录制工具，支持区域截图、窗口截图、滚动截图、OCR 文字识别和截图标注。本仓库提供 CleanShot X 官方安装包下载镜像与历史版本归档，包含原版 DMG 和 SHA-256 校验文件。

### 下载

| 需求 | 下载入口 |
|---|---|
| 最新版本 | [Latest Release](https://github.com/LOVECHEN/cleanshotx-release/releases/latest) |
| 历史版本 / 旧版安装包 | [全部 Releases](https://github.com/LOVECHEN/cleanshotx-release/releases) |
| 5.x 系列 | [CleanShot X 5.x](https://github.com/LOVECHEN/cleanshotx-release/releases?q=mac-5.) |
| 4.x 系列 | [CleanShot X 4.x](https://github.com/LOVECHEN/cleanshotx-release/releases?q=mac-4.) |
| 3.x 系列 | [CleanShot X 3.x](https://github.com/LOVECHEN/cleanshotx-release/releases?q=mac-3.) |

每个版本按 `mac-<版本>` 归档。打开 Release 后展开 **Assets**，下载 `CleanShot-X-<版本>.dmg`；同一页提供发布日期和文件 SHA-256。

### 文件与校验

| 文件 | 内容 |
|---|---|
| `CleanShot-X-<版本>.dmg` | CleanShot X for macOS 安装包 |
| `SHA256SUMS.txt` | 对应安装包的 SHA-256 校验值 |

将安装包与校验文件放在同一目录，在 macOS 终端执行：

```sh
shasum -a 256 -c SHA256SUMS.txt
```

Apple Silicon / Intel Mac 的支持范围及最低 macOS 版本以所选版本为准。

## English

**CleanShot X (CleanShotX / CleanShot for Mac)** is a macOS screenshot and screen recording tool with area capture, window capture, scrolling screenshots, OCR text recognition and screenshot annotation. This repository is an official installer download mirror and historical version archive, providing original DMG packages and SHA-256 checksums.

### Downloads

Open the **[Latest Release](https://github.com/LOVECHEN/cleanshotx-release/releases/latest)** for the newest version, or browse **[all Releases](https://github.com/LOVECHEN/cleanshotx-release/releases)** for older versions.

Quick filters: [5.x](https://github.com/LOVECHEN/cleanshotx-release/releases?q=mac-5.) | [4.x](https://github.com/LOVECHEN/cleanshotx-release/releases?q=mac-4.) | [3.x](https://github.com/LOVECHEN/cleanshotx-release/releases?q=mac-3.)

Releases use the tag `mac-<version>`. Expand **Assets** to download `CleanShot-X-<version>.dmg` and `SHA256SUMS.txt`. Each release lists its publication date and installer checksum.

To verify a download on macOS, place both files in the same directory and run:

```sh
shasum -a 256 -c SHA256SUMS.txt
```

Apple Silicon / Intel Mac support and the minimum macOS version depend on the selected release.
