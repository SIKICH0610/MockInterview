@echo off
rem 启动 Cloudflare 临时公网隧道（需本机 8008 端口的服务已在运行）
rem 窗口里出现 https://xxxx.trycloudflare.com 即为本次的公网地址（每次启动都会变）
"%~dp0tools\cloudflared\cloudflared.exe" tunnel --url http://localhost:8008
