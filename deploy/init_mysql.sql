-- 初始化 MySQL 库与账号（在服务器上执行：sudo mysql < init_mysql.sql）
-- 密码与 backend/.env 里 DATABASE_URL 的密码保持一致。

CREATE DATABASE IF NOT EXISTS dc2
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

CREATE USER IF NOT EXISTS 'dc2'@'localhost'
  IDENTIFIED BY 'CHANGE_ME_DB_PASSWORD';

GRANT ALL PRIVILEGES ON dc2.* TO 'dc2'@'localhost';
FLUSH PRIVILEGES;
