@echo off
echo 🚀 启动智能数据问答系统...

REM 检查依赖
echo 📦 检查依赖...

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ Python 未安装，请先安装 Python 3.8+
    pause
    exit /b 1
)

node --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ Node.js 未安装，请先安装 Node.js 16+
    pause
    exit /b 1
)

REM 检查环境变量文件
if not exist ".env" (
    echo ⚠️  .env 文件不存在，从模板创建...
    copy .env.example .env
    echo 📝 请编辑 .env 文件，添加您的 OpenAI API Key
)

REM 安装后端依赖
echo 📦 安装后端依赖...
cd backend

if not exist "venv" (
    python -m venv venv
)

call venv\Scripts\activate
pip install -r requirements.txt

REM 安装前端依赖
echo 📦 安装前端依赖...
cd ..\frontend
npm install

echo ✅ 依赖安装完成！

REM 启动后端服务
echo 🚀 启动后端服务...
cd ..\backend
start /B cmd /C "call venv\Scripts\activate && python main.py"

REM 等待后端启动
timeout /t 3 /nobreak > nul

REM 启动前端服务
echo 🚀 启动前端服务...
cd ..\frontend
start /B cmd /C "npm run dev"

echo ✅ 系统启动完成！
echo 🌐 前端地址: http://localhost:3000
echo 🔧 后端API: http://localhost:8000
echo.
echo 按任意键退出...
pause > nul