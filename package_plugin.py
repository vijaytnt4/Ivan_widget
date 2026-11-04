"""
Packages the Ivan AI Chatbot WordPress Plugin into a production-ready ZIP archive.
Ensures only required distribution files are included, credentials and test files are excluded,
and the directory structure conforms to WordPress Plugin Manager standards.
"""

import os
import zipfile

PLUGIN_SLUG = "ivan-wordpress"
ZIP_NAME = "ivan-wordpress.zip"

INCLUDED_FILES = [
    "ivan-wordpress.php",
    "includes/class-ivan-admin.php",
    "includes/class-ivan-settings.php",
    "includes/class-ivan-api.php",
    "assets/js/ivan-widget.js",
    "assets/css/ivan-widget.css",
    "assets/images/ivan-avatar.png",
    "readme.txt",
    "uninstall.php"
]

def build_zip():
    print(f"Building {ZIP_NAME}...")
    
    # Remove old zip if exists
    if os.path.exists(ZIP_NAME):
        os.remove(ZIP_NAME)

    with zipfile.ZipFile(ZIP_NAME, "w", zipfile.ZIP_DEFLATED) as zipf:
        for rel_path in INCLUDED_FILES:
            norm_path = os.path.normpath(rel_path)
            if not os.path.exists(norm_path):
                raise FileNotFoundError(f"Missing required file: {norm_path}")
            
            # Destination inside zip: ivan-wordpress/rel_path
            archive_path = f"{PLUGIN_SLUG}/{rel_path.replace(os.sep, '/')}"
            zipf.write(norm_path, archive_path)
            print(f"  + Added: {archive_path}")

    print(f"Verifying {ZIP_NAME}...")
    with zipfile.ZipFile(ZIP_NAME, "r") as zipf:
        namelist = zipf.namelist()
        print(f"Total files in archive: {len(namelist)}")
        for name in namelist:
            print(f"  - {name}")
            # Ensure no credentials or test files are in the zip
            assert not name.endswith(".py"), f"Test file leaked into zip: {name}"
            assert not ".env" in name, f"Env file leaked into zip: {name}"
            assert not ".git" in name, f"Git metadata leaked into zip: {name}"

        # Ensure main plugin file is at ivan-wordpress/ivan-wordpress.php
        assert f"{PLUGIN_SLUG}/ivan-wordpress.php" in namelist, "Main plugin entry point missing from zip!"

    print(f"SUCCESS: {ZIP_NAME} created successfully ({os.path.getsize(ZIP_NAME)} bytes).")

if __name__ == "__main__":
    build_zip()

