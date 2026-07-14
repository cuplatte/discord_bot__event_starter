#!/usr/bin/env bash
# GCE VM内で実行するセットアップスクリプト
set -e

USERNAME=$(whoami)
BOT_DIR="/home/${USERNAME}/bot"

echo "==> パッケージ導入"
sudo apt update
sudo apt install -y python3-pip python3-venv

echo "==> 仮想環境と依存"
cd "${BOT_DIR}"
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install discord.py

echo "==> systemdサービス設置"
# サービスファイル内のプレースホルダを実ユーザー名へ置換
sed "s/YOUR_USERNAME/${USERNAME}/g" discord-bot.service | sudo tee /etc/systemd/system/discord-bot.service > /dev/null

echo "==> bot.env を確認してください（未作成なら例からコピー）"
if [ ! -f "${BOT_DIR}/bot.env" ]; then
  cp bot.env.example bot.env
  echo "   bot.env を作成しました。トークンを記入してください: nano ${BOT_DIR}/bot.env"
fi

echo "==> サービス有効化"
sudo systemctl daemon-reload
sudo systemctl enable discord-bot

echo ""
echo "完了。bot.env にトークンを記入してから以下で起動:"
echo "  sudo systemctl start discord-bot"
echo "  sudo systemctl status discord-bot"
echo "ログ確認: journalctl -u discord-bot -f"
