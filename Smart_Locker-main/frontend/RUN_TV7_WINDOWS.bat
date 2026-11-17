@echo off
setlocal
cd /d "%~dp0"
where node >nul 2>nul
if errorlevel 1 (
  echo [LOI] Chua tim thay Node.js. Cai Node.js 22 LTS tu https://nodejs.org
  pause
  exit /b 1
)
where npm >nul 2>nul
if errorlevel 1 (
  echo [LOI] Chua tim thay npm. Cai lai Node.js 22 LTS.
  pause
  exit /b 1
)
if not exist node_modules (
  echo [TV7] Dang cai thu vien lan dau...
  call npm install
  if errorlevel 1 (
    echo [LOI] npm install that bai. Kiem tra mang va chay lai.
    pause
    exit /b 1
  )
)
echo [TV7] Mo trinh duyet tai http://localhost:5173 sau khi server khoi dong.
call npm run dev
pause
