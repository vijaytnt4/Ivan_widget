"""
Clean ZIP Installation Verification Test.
Extracts ivan-wordpress.zip to an isolated temp folder, checks file presence,
and ensures proper WordPress structure.
"""

import os
import shutil
import tempfile
import zipfile

def verify_zip_installation():
    zip_path = "ivan-wordpress.zip"
    assert os.path.exists(zip_path), "ZIP file does not exist!"
    
    extract_dir = os.path.join(tempfile.gettempdir(), "test_ivan_wp_install")
    if os.path.exists(extract_dir):
        shutil.rmtree(extract_dir)
    os.makedirs(extract_dir)

    print(f"Extracting {zip_path} into {extract_dir}...")
    with zipfile.ZipFile(zip_path, "r") as zipf:
        zipf.extractall(extract_dir)

    # Verify standard WordPress directory structure
    plugin_root = os.path.join(extract_dir, "ivan-wordpress")
    assert os.path.exists(plugin_root), "Plugin folder ivan-wordpress missing after extraction!"

    expected = [
        "ivan-wordpress.php",
        os.path.join("includes", "class-ivan-admin.php"),
        os.path.join("includes", "class-ivan-settings.php"),
        os.path.join("includes", "class-ivan-api.php"),
        os.path.join("assets", "js", "ivan-widget.js"),
        os.path.join("assets", "css", "ivan-widget.css"),
        os.path.join("assets", "images", "ivan-avatar.png"),
        "readme.txt",
        "uninstall.php"
    ]

    for item in expected:
        full_p = os.path.join(plugin_root, item)
        assert os.path.exists(full_p), f"Missing file in extracted plugin: {item}"
        assert os.path.getsize(full_p) > 0, f"Empty file in extracted plugin: {item}"

    # Verify main plugin file starts with standard WordPress plugin header
    with open(os.path.join(plugin_root, "ivan-wordpress.php"), "r", encoding="utf-8") as f:
        header = f.read(500)
        assert "Plugin Name:       Ivan AI Chatbot" in header, "WordPress plugin header missing or corrupted!"

    print("SUCCESS: Clean ZIP extraction test passed completely. Ready for WordPress installation.")
    # Cleanup
    shutil.rmtree(extract_dir)

if __name__ == "__main__":
    verify_zip_installation()

