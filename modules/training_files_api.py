# -*- coding: utf-8 -*-
"""
Training Files API module: Manage training files (Knowledge Base, Style Guide, Price List)
Handles CRUD operations for file-backed training content used by the bot at runtime.
"""

import os
from datetime import datetime
from typing import Optional
from fastapi import HTTPException

from modules.core import app
import config
from storage.persistent_storage import (
    KNOWLEDGE_BASE_FILE,
    STYLE_GUIDE_FILE,
    PRICE_LIST_FILE,
    CONTENT_DIR,
    ensure_dirs,
)

TRAINING_FILES = {
    "knowledge_base": {
        "path": str(KNOWLEDGE_BASE_FILE),
        "name": "Knowledge Base",
        "description": "General knowledge and information the bot can reference",
        "config_attr": "CORE_KNOWLEDGE_BASE",
    },
    "style_guide": {
        "path": str(STYLE_GUIDE_FILE),
        "name": "Style Guide",
        "description": "Bot behavior, tone, and response style guidelines",
        "config_attr": "BOT_STYLE_GUIDE",
    },
    "price_list": {
        "path": str(PRICE_LIST_FILE),
        "name": "Price List",
        "description": "Service pricing information",
        "config_attr": "PRICE_LIST",
    },
}


def ensure_file_exists(file_path: str) -> None:
    """Ensure the file exists, create it with empty content if it doesn't"""
    ensure_dirs()
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    if not os.path.exists(file_path):
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write("")
        print(f"Created empty file: {file_path}")


def reload_config_value(file_id: str, content: str) -> None:
    """Reload the config value for a training file"""
    try:
        file_config = TRAINING_FILES.get(file_id)
        if file_config and hasattr(config, file_config["config_attr"]):
            setattr(config, file_config["config_attr"], content.strip())
            print(f"Reloaded config.{file_config['config_attr']}")
    except Exception as e:
        print(f"Warning: Could not reload config for {file_id}: {e}")


@app.get("/api/training-files/list")
async def list_training_files():
    """List all available training files with metadata"""
    try:
        files = []
        for file_id, file_config in TRAINING_FILES.items():
            file_path = file_config["path"]
            ensure_file_exists(file_path)

            stat = os.stat(file_path)
            files.append({
                "id": file_id,
                "name": file_config["name"],
                "description": file_config["description"],
                "path": file_path,
                "size": stat.st_size,
                "last_modified": datetime.fromtimestamp(stat.st_mtime).isoformat()
            })

        return {
            "success": True,
            "files": files
        }
    except Exception as e:
        print(f"Error listing training files: {e}")
        return {
            "success": False,
            "error": str(e)
        }


@app.get("/api/training-files/{file_id}")
async def get_training_file(file_id: str):
    """Get content of a specific training file"""
    try:
        if file_id not in TRAINING_FILES:
            return {
                "success": False,
                "error": f"Unknown file type: {file_id}"
            }

        file_config = TRAINING_FILES[file_id]
        file_path = file_config["path"]

        # Ensure file exists
        ensure_file_exists(file_path)

        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        stat = os.stat(file_path)

        return {
            "success": True,
            "file_id": file_id,
            "name": file_config["name"],
            "content": content,
            "size": stat.st_size,
            "last_modified": datetime.fromtimestamp(stat.st_mtime).isoformat()
        }
    except Exception as e:
        print(f"Error getting training file {file_id}: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e)
        }


@app.post("/api/training-files/{file_id}")
async def update_training_file(file_id: str, request: dict):
    """Update content of a specific training file"""
    try:
        if file_id not in TRAINING_FILES:
            return {
                "success": False,
                "error": f"Unknown file type: {file_id}"
            }

        content = request.get("content", "")

        # Allow empty content (user might want to clear the file)
        if content is None:
            content = ""

        file_config = TRAINING_FILES[file_id]
        file_path = file_config["path"]

        # Create backup before updating
        backup_path = None
        if os.path.exists(file_path):
            backup_filename = f"{os.path.basename(file_path).replace('.txt', '')}_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            backup_path = str(CONTENT_DIR / backup_filename)
            with open(file_path, 'r', encoding='utf-8') as f:
                backup_content = f.read()
            with open(backup_path, 'w', encoding='utf-8') as f:
                f.write(backup_content)
            print(f"Backup created: {backup_path}")

        # Ensure directory exists
        os.makedirs(os.path.dirname(file_path), exist_ok=True)

        # Write new content
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)

        # Reload config to apply changes immediately
        reload_config_value(file_id, content)

        stat = os.stat(file_path)

        print(f"Training file updated: {file_id} ({file_path})")

        return {
            "success": True,
            "message": f"{file_config['name']} updated successfully",
            "file_id": file_id,
            "backup_created": backup_path,
            "size": stat.st_size,
            "last_modified": datetime.fromtimestamp(stat.st_mtime).isoformat()
        }
    except Exception as e:
        print(f"Error updating training file {file_id}: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e)
        }


@app.get("/api/training-files/{file_id}/backups")
async def list_training_file_backups(file_id: str):
    """List all backups for a specific training file"""
    try:
        if file_id not in TRAINING_FILES:
            return {
                "success": False,
                "error": f"Unknown file type: {file_id}"
            }

        file_config = TRAINING_FILES[file_id]
        data_dir = str(CONTENT_DIR)
        base_name = os.path.basename(file_config["path"]).replace(".txt", "")

        backups = []

        if os.path.exists(data_dir):
            for filename in os.listdir(data_dir):
                if filename.startswith(f"{base_name}_backup_") and filename.endswith('.txt'):
                    filepath = os.path.join(data_dir, filename)
                    backups.append({
                        "filename": filename,
                        "created": datetime.fromtimestamp(os.path.getmtime(filepath)).isoformat(),
                        "size": os.path.getsize(filepath)
                    })

        # Sort by creation time (newest first)
        backups.sort(key=lambda x: x['created'], reverse=True)

        return {
            "success": True,
            "file_id": file_id,
            "backups": backups,
            "total": len(backups)
        }
    except Exception as e:
        print(f"Error listing backups for {file_id}: {e}")
        return {
            "success": False,
            "error": str(e)
        }


@app.post("/api/training-files/{file_id}/restore")
async def restore_training_file_backup(file_id: str, request: dict):
    """Restore a training file from a backup"""
    try:
        if file_id not in TRAINING_FILES:
            return {
                "success": False,
                "error": f"Unknown file type: {file_id}"
            }

        backup_filename = request.get("filename", "")

        if not backup_filename:
            return {
                "success": False,
                "error": "Backup filename is required"
            }

        file_config = TRAINING_FILES[file_id]
        file_path = file_config["path"]
        backup_path = str(CONTENT_DIR / backup_filename)

        if not os.path.exists(backup_path):
            return {
                "success": False,
                "error": "Backup file not found"
            }

        # Read backup content
        with open(backup_path, 'r', encoding='utf-8') as f:
            backup_content = f.read()

        if os.path.exists(file_path):
            current_backup_filename = f"{os.path.basename(file_path).replace('.txt', '')}_backup_before_restore_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            current_backup_path = str(CONTENT_DIR / current_backup_filename)
            with open(file_path, 'r', encoding='utf-8') as f:
                current_content = f.read()
            with open(current_backup_path, 'w', encoding='utf-8') as f:
                f.write(current_content)
            print(f"Current version backed up: {current_backup_path}")

        # Restore from backup
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(backup_content)

        # Reload config
        reload_config_value(file_id, backup_content)

        print(f"Training file restored: {file_id} from {backup_filename}")

        return {
            "success": True,
            "message": f"{file_config['name']} restored from {backup_filename}",
            "last_modified": datetime.now().isoformat()
        }
    except Exception as e:
        print(f"Error restoring backup for {file_id}: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e)
        }


@app.get("/api/training-files/{file_id}/stats")
async def get_training_file_stats(file_id: str):
    """Get statistics about a training file"""
    try:
        if file_id not in TRAINING_FILES:
            return {
                "success": False,
                "error": f"Unknown file type: {file_id}"
            }

        file_config = TRAINING_FILES[file_id]
        file_path = file_config["path"]

        ensure_file_exists(file_path)

        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        lines = content.split('\n')
        words = content.split()

        stat = os.stat(file_path)

        return {
            "success": True,
            "file_id": file_id,
            "stats": {
                "lines": len(lines),
                "words": len(words),
                "characters": len(content),
                "file_size": stat.st_size,
                "last_modified": datetime.fromtimestamp(stat.st_mtime).isoformat()
            }
        }
    except Exception as e:
        print(f"Error getting stats for {file_id}: {e}")
        return {
            "success": False,
            "error": str(e)
        }
