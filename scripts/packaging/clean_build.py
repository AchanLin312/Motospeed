"""
清理打包过程中生成的临时文件
"""
import shutil
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2] if Path(__file__).parent.name == "packaging" else Path(__file__).parent.resolve()

def clean_build():
    """清理构建文件"""
    print("清理打包临时文件...")
    
    # 清理目录
    dirs_to_clean = [
        PROJECT_ROOT / "dist",
        PROJECT_ROOT / "build",
        PROJECT_ROOT / "__pycache__",
    ]
    
    for dir_path in dirs_to_clean:
        if dir_path.exists():
            try:
                shutil.rmtree(dir_path)
                print(f"✓ 已删除: {dir_path}")
            except Exception as e:
                print(f"✗ 删除失败 {dir_path}: {e}")
    
    # 清理spec文件
    spec_files = [
        PROJECT_ROOT / "backend.spec",
        PROJECT_ROOT / "ui.spec",
    ]
    
    for spec_file in spec_files:
        if spec_file.exists():
            try:
                spec_file.unlink()
                print(f"✓ 已删除: {spec_file}")
            except Exception as e:
                print(f"✗ 删除失败 {spec_file}: {e}")
    
    print("\n清理完成！可以重新运行 build_package.py")

if __name__ == "__main__":
    clean_build()

