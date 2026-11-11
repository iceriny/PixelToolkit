# PixelToolkit 像素工坊

[![Test and release](https://github.com/iceriny/PixelToolkit/actions/workflows/ci-release.yml/badge.svg)](https://github.com/iceriny/PixelToolkit/actions/workflows/ci-release.yml)
[![Release](https://img.shields.io/github/v/release/iceriny/PixelToolkit)](https://github.com/iceriny/PixelToolkit/releases/latest)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

一组可独立使用的高清图转像素图工具。适用于图标、游戏精灵、材质、界面组件和低分辨率插图。输入 PNG、JPEG、WebP、BMP 或 TIFF，导出原像素尺寸的 RGBA PNG。

## 打开工作台

Windows 可从 [Releases](https://github.com/iceriny/PixelToolkit/releases/latest) 下载 `windows-x64.zip`，解压后双击 `PixelToolkit.exe`。便携版已包含 Python 运行环境和依赖，命令行执行 `PixelToolkit.exe --help` 可使用完整工具组。

源码方式可先安装 [uv](https://docs.astral.sh/uv/getting-started/installation/)，再双击 Windows 的 [启动.cmd](启动.cmd)。首次运行自动安装 Python 依赖，随后在浏览器打开本地工作台。命令行适用于 Windows、Linux 和 macOS。

```powershell
cd PixelToolkit
uv run pixeltoolkit gui
```

选择一张或多张图片，调整目标尺寸、颜色上限、透明处理和留边，再点「转换当前图片」。结果可在深色、浅色和棋盘底之间切换，查看原尺寸与最近邻放大效果。下载的文件保持目标像素尺寸。

「批量导出 ZIP」会把全部选中图片放入同一个压缩包，包含 `images/`、`previews/` 和 `settings.json`。批量默认提取共享色板，保存为 `palette.json`。粘贴固定色板后，优先使用该色板。统一色板可减少一组物品和逐帧素材之间的色差。

工作台只在 `127.0.0.1` 提供服务。关闭启动窗口或按 Ctrl+C 结束服务。图片在本机处理，成品由浏览器下载。输入合计约 46 MB、最多 100 张，工作台目标单边最多 512 像素。更大的批量目录可用命令行。

## 工具组

| 命令 | 用途 |
| --- | --- |
| `gui` | 本地可视化工作台，支持单图预览、批量 ZIP、参数文件和色板。 |
| `convert` | 单图转换，可另外保存深浅底预览。 |
| `batch` | 批量或递归目录转换，支持统一色板、预览与逐文件结果报告。 |
| `palette` | 从单图或同组图片提取色板，导出 JSON 或 GIMP GPL。 |
| `compare` | 对比同一张图在不同颜色上限下的结果。 |
| `sheet` | 把已导出素材排成带文件名的联系表。 |
| `inspect` | 查看尺寸、可见颜色数、透明与半透明像素数。 |
| `config` | 导出可复用的转换参数。 |

在本目录运行以下命令。所有路径均可使用带引号的绝对路径。用 `uv run pixeltoolkit <命令> --help` 查看参数。

```powershell
# 单图与深浅底预览
uv run pixeltoolkit convert "D:\原图\道具.png" "D:\成品\道具.png" --preset sprite --preview "D:\成品\道具-preview.png"

# 64×48 像素，保留半透明
uv run pixeltoolkit convert "D:\原图\玻璃.png" "D:\成品\玻璃.png" --size 64x48 --alpha keep --padding 1

# 递归处理同一套素材，结果保持输入目录层级
uv run pixeltoolkit batch "D:\原图" "D:\成品套装" --recursive --shared-palette --colors 24 --previews

# 提取和复用色板
uv run pixeltoolkit palette "D:\原图" "D:\配色\套装.json" --colors 24 --recursive
uv run pixeltoolkit convert "D:\原图\道具.png" "D:\成品\道具.png" --palette "D:\配色\套装.json" --overwrite
uv run pixeltoolkit palette "D:\原图" "D:\配色\套装.gpl" --colors 16

# 对比 8／16／24／32 色
uv run pixeltoolkit compare "D:\原图\道具.png" "D:\成品\减色对照.png" --color-counts 8 16 24 32

# 联系表、图像检查
uv run pixeltoolkit sheet "D:\成品套装\images" "D:\成品套装\联系表.png" --recursive --columns 5 --scale 4
uv run pixeltoolkit inspect "D:\成品套装\images" --recursive

# 保存并复用参数
uv run pixeltoolkit config "D:\配色\图标参数.json" --preset icon --detail 0.8
uv run pixeltoolkit convert "D:\原图\道具.png" "D:\成品\道具.png" --config "D:\配色\图标参数.json" --overwrite
```

输出文件已存在时，默认拒绝写入，明确加 `--overwrite` 才替换。输出不能覆盖输入图，批量输出目录应放在输入目录外。同一个目录中的 `a.jpg` 和 `a.png` 会产生输出重名，工具会在写入之前报告。递归模式中不同子目录里的同名图片按原层级保留。

批量任务会继续处理其他文件，并把失败原因记在 `report.json`。存在失败时命令退出码为 1。参数或路径错误为 2，正常完成为 0。

## 预设和调节

| 预设 | 默认尺寸 | 颜色上限 | 留边 | 透明处理 |
| --- | --- | --- | --- | --- |
| `icon` | 16×16 | 14 | 1 | 二值 |
| `sprite` | 32×32 | 24 | 2 | 二值 |
| `texture` | 32×32 | 16 | 0 | 保留，铺满画布 |
| `illustration` | 160×96 | 32 | 0 | 保留原构图 |
| `ui` | 64×64 | 24 | 0 | 保留原构图 |

参数按预设、参数 JSON、显式命令行参数的顺序覆盖。工作台导出的参数 JSON 可直接交给命令行 `--config`。

- `--detail 0～2` 提高轮廓和局部颜色的采样权重，默认 0.55。
- `--cleanup 0～1` 合并非常接近相邻颜色的孤立像素，默认 0.045。0 为关闭。
- `--saturation 0～2` 调节饱和度，默认 1。
- `--alpha keep` 保留玻璃、雾和光效的半透明。`cutout` 用 `--threshold` 决定轮廓。
- `--backdrop FFFFFF --tolerance 24` 去除与图边相连的近白背景。只有明确纯色背景适合这样处理。
- `--no-trim` 保留输入画布上的留白与位置，适合同画布动画帧。`--tile` 则把整个输入直接映射到目标宽高。
- `--size` 支持正方形和矩形，命令行单边范围为 1～1024。材质是否无缝取决于源图，`texture` 预设只负责尺寸和减色。

## 色板格式

`--palette` 接受本工具的 JSON 和 GPL 文件。JSON 的 `colors` 可写六位十六进制颜色或 RGB 三元组，也接受单独的颜色数组。项目式的“分组名 → 颜色数组”字典也可读取。

```json
{
  "colors": ["#302A32", "#725442", "#BFA67F", "#E8D9B8"]
}
```

## 供其他程序调用

可以用 `pip install .` 安装本目录，然后导入同一转换引擎。

```python
from pathlib import Path
from pixeltoolkit.workflow import Settings, read_palette

settings = Settings.resolve("sprite", overrides={"size": [32, 24], "padding": 1})
palette = read_palette("palette.json")
result = settings.convert(Path("source.png"), palette)
result.save("pixel.png")
```

## 实现与质量

引擎整理自项目已有的 `pixelize_asset.py`，使用有界过采样、透明覆盖率、局部边缘权重、Oklab 色板拟合和孤立近色合并。透明像素不参加色板拟合，色板拟合限制代表样本数，整图颜色映射分块计算。输出不自动加入抖动。

这些步骤能保留小尺寸轮廓和有组织的色块。复杂文字、极细线条、多人物场景缩到 16×16 时仍需要人工取舍。颜色上限、分辨率和适当的原图构图共同决定结果。

原始算法参考资料沿用在 [算法说明](算法说明.md)。回归检查用 `uv run python -m unittest discover -s tests -v`，覆盖两种入口输出一致、递归批量与共享色板、源文件保护、色板与配置往返、半透明及工作台 ZIP 内容。

## 版本发布

提交到 `main` 或打开 Pull Request 会自动运行 Windows、Linux 和 Python 3.11／3.13 的回归检查。发布时更新 `pyproject.toml` 中的版本与 `RELEASE_NOTES.md`，提交后创建同版本的标签。

```sh
git tag v1.0.0
git push origin v1.0.0
```

标签版本须与包版本一致。检查全部通过后，GitHub Actions 自动生成 wheel、源码包、Windows x64 便携 ZIP 和 SHA-256 校验文件，再创建 GitHub Release。同一标签的任务重跑可重新上传对应文件。

项目采用 [MIT 许可证](LICENSE)。
