@echo off
rem ============================================================
rem Motospeed V2 local launcher TEMPLATE (no real keys inside)
rem Usage: copy this file to start_v2.bat, then edit the LLM_*
rem   lines with your own credentials. start_v2.bat is
rem   gitignored and must never be committed.
rem   - Values set in Windows system env vars take precedence
rem ============================================================
if not defined LLM_API_BASE set "LLM_API_BASE=https://api.deepseek.com/v1"
if not defined LLM_API_KEY  set "LLM_API_KEY=sk-在此填入你的LLM密钥"
if not defined LLM_MODEL    set "LLM_MODEL=deepseek-chat"
if not defined V2_ADMIN_TOKEN set "V2_ADMIN_TOKEN=在此填入一个随机管理令牌"
rem --- LAN proxy is OPT-IN: enabled only when use_proxy.flag exists
rem --- next to this bat. Direct-internet machines need NO change.
rem --- If needed, create use_proxy.flag and edit the proxy below.
if exist "%~dp0use_proxy.flag" (
  set "HTTP_PROXY=http://your-proxy-host:8089"
  set "HTTPS_PROXY=http://your-proxy-host:8089"
)
set "NO_PROXY=127.0.0.1,localhost"
cd /d "%~dp0"
"venv\Scripts\python.exe" backend\run.py
