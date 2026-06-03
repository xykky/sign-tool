#!/bin/bash
# ===========================================
#  Sign Tool 更新脚本
#  用法: sudo bash update.sh
# ===========================================

set -e

INSTALL_DIR="/opt/sign-tool"

if [ ! -d "$INSTALL_DIR/.git" ]; then
    echo "错误: $INSTALL_DIR 不是 git 仓库，请先运行 install.sh"
    exit 1
fi

cd "$INSTALL_DIR"

echo "=========================================="
echo "  Sign Tool 更新"
echo "=========================================="
echo ""

# 1. 拉取最新代码
echo "[1/3] 拉取最新代码..."
OLD_COMMIT=$(git rev-parse --short HEAD)
git pull --ff-only || {
    echo "  git pull 失败，尝试 reset..."
    git fetch origin
    git reset --hard origin/master
}
NEW_COMMIT=$(git rev-parse --short HEAD)

if [ "$OLD_COMMIT" = "$NEW_COMMIT" ]; then
    echo "  已是最新版本 ($OLD_COMMIT)"
else
    echo "  已更新: $OLD_COMMIT -> $NEW_COMMIT"
fi

# 2. 更新依赖
echo "[2/3] 更新 Python 依赖..."
source .venv/bin/activate
pip install -e . -q

# 3. 重启服务
echo "[3/3] 重启服务..."
systemctl restart sign-tool
echo "  服务已重启"

echo ""
echo "=========================================="
echo "  更新完成！"
echo "=========================================="
echo ""
echo "  查看日志: journalctl -u sign-tool -f"
echo ""
