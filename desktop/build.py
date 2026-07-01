import os
import sys
import subprocess
import shutil

def run_command(cmd, cwd=None):
    print(f"Running: {cmd} in {cwd or '.'}")
    res = subprocess.run(cmd, shell=True, cwd=cwd)
    if res.returncode != 0:
        print(f"Error: Command failed with exit code {res.returncode}")
        sys.exit(1)

def main():
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    frontend_dir = os.path.join(root_dir, "frontend")
    
    # 1. Build Vue Frontend
    print("=== Step 1: Building Frontend Vue 3 App ===")
    if not os.path.exists(os.path.join(frontend_dir, "node_modules")):
        run_command("npm install", cwd=frontend_dir)
    run_command("npm run build", cwd=frontend_dir)

    # 2. Package Backend with PyInstaller
    print("=== Step 2: Packaging Python App with PyInstaller ===")
    sep = ";" if sys.platform == "win32" else ":"
    
    # Check if pyinstaller is installed
    try:
        import PyInstaller
    except ImportError:
        print("Installing PyInstaller...")
        run_command(f"{sys.executable} -m pip install pyinstaller")

    # Clean previous build directories
    dist_dir = os.path.join(root_dir, "dist")
    build_dir = os.path.join(root_dir, "build")
    for d in [dist_dir, build_dir]:
        if os.path.exists(d):
            shutil.rmtree(d)

    # Invoke PyInstaller with exclusions to avoid Qt conflict and heavy scientific packages
    exclusions = [
        "PyQt5", "PyQt6", "PySide2", "PySide6", "tkinter", 
        "matplotlib", "notebook", "ipykernel", "qtpy", "jedi", 
        "PIL", "babel", "sphinx", "numpy", "pandas"
    ]
    exclude_str = " ".join([f"--exclude-module {mod}" for mod in exclusions])

    pyinstaller_cmd = (
        f"pyinstaller --noconfirm --onefile --console "
        f"--add-data \"app/static{sep}app/static\" "
        f"{exclude_str} "
        f"\"web_app.py\""
    )
    run_command(pyinstaller_cmd, cwd=root_dir)
    print("=== Packaging Completed! Output executable is located in 'dist/' ===")

if __name__ == "__main__":
    main()
