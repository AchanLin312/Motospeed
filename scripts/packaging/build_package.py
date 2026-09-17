"""
数治骑迹平台打包脚本
支持两种打包方式：
1. PyInstaller打包（Windows单文件exe）
2. 创建便携式安装包
"""
import os
import sys
import shutil
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2] if Path(__file__).parent.name == "packaging" else Path(__file__).parent.resolve()


def check_dependencies():
    """检查打包依赖"""
    print("检查打包依赖...")
    try:
        import PyInstaller
        print("✓ PyInstaller 已安装")
    except ImportError:
        print("✗ PyInstaller 未安装，正在安装...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])
        print("✓ PyInstaller 安装完成")


def create_backend_spec():
    """创建后端Flask应用的spec文件"""
    # 动态构建datas列表，只包含存在的目录
    datas = []
    
    # 检查并添加templates目录
    templates_dir = PROJECT_ROOT / "backend" / "app" / "templates"
    if templates_dir.exists() and templates_dir.is_dir():
        datas.append(('backend/app/templates', 'app/templates'))
        print(f"  ✓ 添加模板目录: {templates_dir}")
    else:
        print(f"  ⚠ 警告: 模板目录不存在: {templates_dir}")
    
    # 检查并添加spatial_analysis目录
    spatial_dir = PROJECT_ROOT / "spatial_analysis"
    if spatial_dir.exists() and spatial_dir.is_dir():
        datas.append(('spatial_analysis', 'spatial_analysis'))
        print(f"  ✓ 添加算法目录: {spatial_dir}")
    else:
        print(f"  ⚠ 警告: 算法目录不存在: {spatial_dir}")
    
    # 检查static目录（可选）
    static_dir = PROJECT_ROOT / "backend" / "app" / "static"
    if static_dir.exists() and static_dir.is_dir():
        datas.append(('backend/app/static', 'app/static'))
        print(f"  ✓ 添加静态文件目录: {static_dir}")
    
    # 将datas列表转换为字符串格式
    if not datas:
        print("  ✗ 错误: 没有找到任何数据目录")
        return None
    
    datas_str = ",\n        ".join([f"('{src}', '{dst}')" for src, dst in datas])
    
    # 添加项目根目录到路径
    project_root_str = str(PROJECT_ROOT).replace('\\', '\\\\')
    
    spec_content = f"""# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['backend/run.py'],
    pathex=['{project_root_str}'],
    binaries=[],
    datas=[
        {datas_str},
    ],
    hiddenimports=[
        'flask',
        'pandas',
        'geopandas',
        'libpysal',
        'esda',
        'pymannkendall',
        'PyQt6',
        'PyQt6.QtWebEngineWidgets',
        'matplotlib',
        'folium',
        'python-docx',
        'openpyxl',
        'Pillow',
    ],
    hookspath=[],
    hooksconfig={{}},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='数治骑迹-后端服务',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # 显示控制台窗口，方便查看日志
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
"""
    spec_file = PROJECT_ROOT / "backend.spec"
    with open(spec_file, "w", encoding="utf-8") as f:
        f.write(spec_content)
    print(f"✓ 已创建后端spec文件: {spec_file}")
    print(f"  包含 {len(datas)} 个数据目录")
    return spec_file


def create_ui_spec():
    """创建PyQt6桌面端的spec文件"""
    # 动态构建datas列表，只包含存在的文件/目录
    datas = []
    
    # 检查并添加spatial_analysis目录
    spatial_dir = PROJECT_ROOT / "spatial_analysis"
    if spatial_dir.exists() and spatial_dir.is_dir():
        datas.append(('spatial_analysis', 'spatial_analysis'))
        print(f"  ✓ 添加算法目录: {spatial_dir}")
    else:
        print(f"  ⚠ 警告: 算法目录不存在: {spatial_dir}")
    
    # 检查templates目录是否存在
    templates_dir = PROJECT_ROOT / "backend" / "app" / "templates"
    if templates_dir.exists() and templates_dir.is_dir():
        datas.append(('backend/app/templates', 'app/templates'))
        print(f"  ✓ 添加模板目录: {templates_dir}")
    else:
        print(f"  ⚠ 警告: 模板目录不存在: {templates_dir}")
    
    # 将datas列表转换为字符串格式
    if not datas:
        print("  ✗ 错误: 没有找到任何数据目录")
        return None
    
    datas_str = ",\n        ".join([f"('{src}', '{dst}')" for src, dst in datas])
    
    # 添加项目根目录到路径
    project_root_str = str(PROJECT_ROOT).replace('\\', '\\\\')
    
    spec_content = f"""# -*- mode: python ; coding: utf-8 -*-
import PyInstaller.utils.hooks as hooks

block_cipher = None

# 收集PyQt6的所有子模块和数据文件
pyqt6_datas, pyqt6_binaries, pyqt6_hiddenimports = hooks.collect_all('PyQt6')

# 收集QtWebEngine的特殊文件
try:
    webengine_datas, webengine_binaries, webengine_hiddenimports = hooks.collect_all('PyQt6.QtWebEngineWidgets')
    pyqt6_datas += webengine_datas
    pyqt6_binaries += webengine_binaries
    pyqt6_hiddenimports += webengine_hiddenimports
except:
    pass

a = Analysis(
    ['ui/main_ui.py'],
    pathex=['{project_root_str}'],
    binaries=pyqt6_binaries + [],
    datas=pyqt6_datas + [
        {datas_str},
    ],
    hiddenimports=pyqt6_hiddenimports + [
        'PyQt6',
        'PyQt6.QtCore',
        'PyQt6.QtGui',
        'PyQt6.QtWidgets',
        'PyQt6.QtWebEngineWidgets',
        'PyQt6.QtWebEngineCore',
        'PyQt6.QtNetwork',
        'PyQt6.QtWebEngine',
        'backend.app',
        'spatial_analysis',
    ],
    hookspath=[],
    hooksconfig={{}},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='数治骑迹-桌面端',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # 禁用UPX压缩，避免破坏DLL
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # 临时启用控制台，方便调试
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
"""
    spec_file = PROJECT_ROOT / "ui.spec"
    with open(spec_file, "w", encoding="utf-8") as f:
        f.write(spec_content)
    print(f"✓ 已创建桌面端spec文件: {spec_file}")
    print(f"  包含 {len(datas)} 个数据目录/文件")
    return spec_file


def build_backend():
    """打包后端Flask应用"""
    print("\n开始打包后端服务...")
    
    # 检查必要文件是否存在
    run_file = PROJECT_ROOT / "backend" / "run.py"
    if not run_file.exists():
        print(f"✗ 错误: 找不到 {run_file}")
        return False
    
    templates_dir = PROJECT_ROOT / "backend" / "app" / "templates"
    if not templates_dir.exists():
        print(f"✗ 错误: 找不到 {templates_dir}")
        return False
    
    spatial_analysis_dir = PROJECT_ROOT / "spatial_analysis"
    if not spatial_analysis_dir.exists():
        print(f"✗ 错误: 找不到 {spatial_analysis_dir}")
        return False
    
    spec_file = create_backend_spec()
    if spec_file is None:
        return False
    
    try:
        cmd = [
            sys.executable, "-m", "PyInstaller",
            "--clean",
            "--noconfirm",
            str(spec_file)
        ]
        
        subprocess.check_call(cmd)
        print("✓ 后端服务打包完成")
        exe_path = PROJECT_ROOT / "dist" / "数治骑迹-后端服务.exe"
        if exe_path.exists():
            print(f"  输出文件: {exe_path}")
            print(f"  文件大小: {exe_path.stat().st_size / 1024 / 1024:.1f} MB")
        return True
    except subprocess.CalledProcessError as e:
        print(f"✗ 打包失败: {e}")
        return False


def build_ui():
    """打包PyQt6桌面端"""
    print("\n开始打包桌面端...")
    
    # 检查必要文件是否存在
    ui_file = PROJECT_ROOT / "ui" / "main_ui.py"
    if not ui_file.exists():
        print(f"✗ 错误: 找不到 {ui_file}")
        return False
    
    spec_file = create_ui_spec()
    if spec_file is None:
        return False
    
    try:
        cmd = [
            sys.executable, "-m", "PyInstaller",
            "--clean",
            "--noconfirm",
            str(spec_file)
        ]
        
        subprocess.check_call(cmd)
        print("✓ 桌面端打包完成")
        exe_path = PROJECT_ROOT / "dist" / "数治骑迹-桌面端.exe"
        if exe_path.exists():
            print(f"  输出文件: {exe_path}")
            print(f"  文件大小: {exe_path.stat().st_size / 1024 / 1024:.1f} MB")
        return True
    except subprocess.CalledProcessError as e:
        print(f"✗ 打包失败: {e}")
        return False


def create_portable_package():
    """创建便携式安装包"""
    print("\n创建便携式安装包...")
    
    package_dir = PROJECT_ROOT / "数治骑迹-便携版"
    if package_dir.exists():
        shutil.rmtree(package_dir)
    package_dir.mkdir()
    
    # 复制可执行文件
    dist_dir = PROJECT_ROOT / "dist"
    if (dist_dir / "数治骑迹-后端服务.exe").exists():
        shutil.copy2(dist_dir / "数治骑迹-后端服务.exe", package_dir)
    if (dist_dir / "数治骑迹-桌面端.exe").exists():
        shutil.copy2(dist_dir / "数治骑迹-桌面端.exe", package_dir)
    
    # 创建必要的目录
    (package_dir / "outputs").mkdir()
    (package_dir / "uploads").mkdir()
    
    # 创建启动脚本
    start_script = package_dir / "启动服务.bat"
    with open(start_script, "w", encoding="utf-8") as f:
        f.write("""@echo off
setlocal EnableExtensions
set "SCRIPT_DIR=%~dp0"
set "PROJECT_ROOT=%SCRIPT_DIR%.."
set "SOURCE_PY=E:\\Anaconda\\envs\\MCM\\python.exe"
set "BACKEND_RUN=%PROJECT_ROOT%\\backend\\run.py"
set "VENDOR_DIR=%PROJECT_ROOT%\\.vendor"

echo Starting backend service...

if exist "%SOURCE_PY%" if exist "%BACKEND_RUN%" (
    if exist "%VENDOR_DIR%" set "PYTHONPATH=%VENDOR_DIR%;%PYTHONPATH%"
    echo Using source backend with MCM environment.
    start "backend" "%SOURCE_PY%" "%BACKEND_RUN%"
    echo Backend started. Open http://127.0.0.1:5000 in your browser.
    echo Close this window at any time. The service will keep running.
    pause
    exit /b 0
)

for /f "usebackq delims=" %%F in (`powershell -NoProfile -ExecutionPolicy Bypass -Command "(Get-ChildItem -LiteralPath '%SCRIPT_DIR%' -Filter *.exe | Sort-Object Length | Select-Object -First 1 -ExpandProperty FullName)"`) do set "BACKEND_EXE=%%F"

if not defined BACKEND_EXE (
    echo Backend executable was not found.
    pause
    exit /b 1
)

start "backend" "%BACKEND_EXE%"
echo Backend started. Open http://127.0.0.1:5000 in your browser.
echo Close this window at any time. The service will keep running.
pause
""")

    desktop_script = package_dir / "启动桌面端.bat"
    with open(desktop_script, "w", encoding="utf-8") as f:
        f.write("""@echo off
setlocal EnableExtensions
set "SCRIPT_DIR=%~dp0"
set "PROJECT_ROOT=%SCRIPT_DIR%.."
set "SOURCE_PY=E:\\Anaconda\\envs\\MCM\\python.exe"
set "UI_MAIN=%PROJECT_ROOT%\\ui\\main_ui.py"
set "VENDOR_DIR=%PROJECT_ROOT%\\.vendor"

echo Starting desktop application...

if exist "%SOURCE_PY%" if exist "%UI_MAIN%" (
    "%SOURCE_PY%" -c "import PyQt6" >nul 2>nul
    if not errorlevel 1 (
        if exist "%VENDOR_DIR%" set "PYTHONPATH=%VENDOR_DIR%;%PYTHONPATH%"
        echo Using source desktop app with MCM environment.
        start "desktop" "%SOURCE_PY%" "%UI_MAIN%"
        exit /b 0
    )
)

for /f "usebackq delims=" %%F in (`powershell -NoProfile -ExecutionPolicy Bypass -Command "(Get-ChildItem -LiteralPath '%SCRIPT_DIR%' -Filter *.exe | Sort-Object Length -Descending | Select-Object -First 1 -ExpandProperty FullName)"`) do set "DESKTOP_EXE=%%F"

if not defined DESKTOP_EXE (
    echo Desktop executable was not found.
    pause
    exit /b 1
)

start "desktop" "%DESKTOP_EXE%"
""")
    
    # 创建使用说明
    readme = package_dir / "使用说明.txt"
    with open(readme, "w", encoding="utf-8") as f:
        f.write("""数治骑迹平台 - 便携版使用说明
=====================================

一、启动方式
-----------
1. 双击"启动服务.bat"启动后端服务
2. 在浏览器访问 http://127.0.0.1:5000 使用Web版
3. 双击"启动桌面端.bat"优先使用源码桌面版，若源码不可用则自动回退到桌面端exe
4. 也可直接双击"数治骑迹-桌面端.exe"使用桌面版

二、注意事项
-----------
1. 首次运行可能需要几秒钟初始化
2. 确保防火墙允许5000端口访问
3. 数据文件保存在 outputs 和 uploads 目录
4. 如需停止服务，关闭后端服务窗口即可

三、系统要求
-----------
- Windows 10/11 (64位)
- 至少 4GB 内存
- 至少 2GB 可用磁盘空间

四、技术支持
-----------
如遇问题，请查看 outputs/logs 目录下的日志文件
""")
    
    print(f"✓ 便携式安装包创建完成: {package_dir}")
    print(f"  包含文件:")
    for file in package_dir.iterdir():
        print(f"    - {file.name}")


def main():
    """主函数"""
    print("=" * 60)
    print("数治骑迹平台 - 打包工具")
    print("=" * 60)
    
    check_dependencies()
    
    print("\n请选择打包方式:")
    print("1. 仅打包后端服务 (Flask)")
    print("2. 仅打包桌面端 (PyQt6)")
    print("3. 打包后端 + 桌面端")
    print("4. 打包后端 + 桌面端 + 创建便携版")
    
    choice = input("\n请输入选项 (1-4): ").strip()
    
    success = True
    if choice == "1":
        success = build_backend()
    elif choice == "2":
        success = build_ui()
    elif choice == "3":
        backend_ok = build_backend()
        ui_ok = build_ui()
        success = backend_ok and ui_ok
    elif choice == "4":
        backend_ok = build_backend()
        ui_ok = build_ui()
        success = backend_ok and ui_ok
        if success:
            create_portable_package()
    else:
        print("无效选项")
        return
    
    if not success:
        print("\n⚠️  打包过程中出现错误，请检查上述错误信息")
        return
    
    print("\n" + "=" * 60)
    print("打包完成！")
    print("=" * 60)


if __name__ == "__main__":
    main()

