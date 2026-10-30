#!/usr/bin/env bash
# 豆卫兵后端服务器初始化脚本（Ubuntu 22.04 / 24.04）
# 用法：sudo bash provision.sh api.yourdomain.com
# 前提：已把 backend/ 整个目录（含 models/、.env）上传到 /opt/dc2/backend
set -euo pipefail

DOMAIN="${1:-api.douweibing.cn}"
APP_USER="dc2"
APP_DIR="/opt/dc2"

if [ ! -d "$APP_DIR/backend" ]; then
  echo "错误：未找到 $APP_DIR/backend，请先上传 backend 目录。"
  exit 1
fi

echo "==> 1/7 安装系统包"
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y \
  python3 python3-venv python3-pip \
  nginx mariadb-server \
  certbot python3-certbot-nginx \
  curl rsync unzip

echo "==> 2/7 创建部署用户与目录"
id -u "$APP_USER" >/dev/null 2>&1 || useradd --system --create-home --shell /bin/bash "$APP_USER"
mkdir -p "$APP_DIR/data/spatial"
chown -R "$APP_USER:$APP_USER" "$APP_DIR"

echo "==> 3/7 创建虚拟环境并安装依赖"
if [ ! -d "$APP_DIR/backend/.venv" ]; then
  su - "$APP_USER" -c "python3 -m venv $APP_DIR/backend/.venv"
fi
su - "$APP_USER" -c "$APP_DIR/backend/.venv/bin/pip install -U pip"
su - "$APP_USER" -c "$APP_DIR/backend/.venv/bin/pip install -r $APP_DIR/backend/requirements.txt"

echo "==> 4/7 启动数据库"
systemctl enable --now mariadb
# 表结构由后端启动时 create_all 自动建；先初始化库与账号：
sudo mysql < "$APP_DIR/deploy/init_mysql.sql"
# 灌入病害/防治/药剂/图谱种子数据（幂等，已有则跳过）
su - "$APP_USER" -c "cd $APP_DIR/backend && .venv/bin/python -m app.data.seed"

echo "==> 5/7 配置 nginx"
ln -sf "$APP_DIR/deploy/nginx.conf" /etc/nginx/sites-available/dc2-api.conf
ln -sf /etc/nginx/sites-available/dc2-api.conf /etc/nginx/sites-enabled/dc2-api.conf
rm -f /etc/nginx/sites-enabled/default
# 证书未签发前先用临时自签占位，否则 nginx -t 会报证书缺失
if [ ! -f /etc/letsencrypt/live/"$DOMAIN"/fullchain.pem ]; then
  mkdir -p /etc/nginx/ssl
  openssl req -x509 -nodes -days 90 -newkey rsa:2048 \
    -keyout /etc/nginx/ssl/dc2-selfsigned.key \
    -out  /etc/nginx/ssl/dc2-selfsigned.crt \
    -subj "/CN=$DOMAIN" 2>/dev/null
  sed -i "s|/etc/letsencrypt/live/$DOMAIN/fullchain.pem|/etc/nginx/ssl/dc2-selfsigned.crt|" \
        /etc/nginx/sites-available/dc2-api.conf
  sed -i "s|/etc/letsencrypt/live/$DOMAIN/privkey.pem|/etc/nginx/ssl/dc2-selfsigned.key|" \
        /etc/nginx/sites-available/dc2-api.conf
  sed -i "s|api.douweibing.cn|$DOMAIN|g" /etc/nginx/sites-available/dc2-api.conf
fi
nginx -t
systemctl reload nginx

echo "==> 6/7 注册系统服务"
ln -sf "$APP_DIR/deploy/dc2-api.service" /etc/systemd/system/dc2-api.service
systemctl daemon-reload
systemctl enable dc2-api
systemctl restart dc2-api
sleep 2
systemctl --no-pager status dc2-api --lines=15

echo "==> 7/7 本机探活（应输出 OK）"
curl -fsS http://127.0.0.1:8000/api/health && echo " OK"

echo ""
echo "部署完成。备案通过后执行正式证书签发："
echo "  sudo certbot --nginx -d $DOMAIN --agree-tos --no-eff-email -m you@example.com --redirect"
echo "  sudo systemctl restart dc2-api"
