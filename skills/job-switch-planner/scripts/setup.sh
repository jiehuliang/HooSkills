#!/bin/bash
# Job Switch Planner — 安装依赖
set -e

echo "=== 安装 OpenCLI ==="
if command -v opencli &>/dev/null; then
    echo "✅ OpenCLI 已安装: $(opencli --version)"
else
    echo "正在安装 OpenCLI..."
    npm install -g @jackwener/opencli
    echo "✅ 安装完成: $(opencli --version)"
fi

echo ""
echo "=== 首次使用需登录认证 ==="
echo "运行以下命令完成各平台登录："
echo "  opencli zhihu search \"test\"   # 知乎"
echo "  opencli boss search \"test\"    # Boss直聘"
echo "  opencli reddit search \"test\"  # Reddit"
echo ""
echo "首次运行时会自动打开浏览器引导登录。"
