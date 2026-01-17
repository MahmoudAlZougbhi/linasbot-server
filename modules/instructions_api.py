# -*- coding: utf-8 -*-
"""
Instructions API module: Bot Instructions Management
Handles CRUD operations for bot behavior instructions that guide AI responses.
"""

import os
from datetime import datetime
from typing import Optional
from fastapi import HTTPException

from modules.core import app
import config


@app.get("/api/instructions/get")
async def get_instructions():
    """Get current bot instructions"""
    try:
        # Read from file
        instructions_path = 'data/style_guide.txt'
        
        if not os.path.exists(instructions_path):
            return {
                "success": False,
                "error": "Instructions file not found"
            }
        
        with open(instructions_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        return {
            "success": True,
            "instructions": content,
            "last_modified": datetime.fromtimestamp(os.path.getmtime(instructions_path)).isoformat()
        }
    except Exception as e:
        print(f"❌ Error in get_instructions: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e)
        }


@app.post("/api/instructions/update")
async def update_instructions(request: dict):
    """Update bot instructions"""
    try:
        new_instructions = request.get("instructions", "")
        
        if not new_instructions or not new_instructions.strip():
            return {
                "success": False,
                "error": "Instructions cannot be empty"
            }
        
        instructions_path = 'data/style_guide.txt'
        
        # Create backup before updating
        backup_path = f'data/style_guide_backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.txt'
        if os.path.exists(instructions_path):
            with open(instructions_path, 'r', encoding='utf-8') as f:
                backup_content = f.read()
            with open(backup_path, 'w', encoding='utf-8') as f:
                f.write(backup_content)
            print(f"✅ Backup created: {backup_path}")
        
        # Write new instructions
        with open(instructions_path, 'w', encoding='utf-8') as f:
            f.write(new_instructions)
        
        # Reload config to apply changes immediately
        config.BOT_STYLE_GUIDE = new_instructions.strip()
        print(f"✅ Bot instructions updated and reloaded into memory")
        
        return {
            "success": True,
            "message": "Instructions updated successfully",
            "backup_created": backup_path,
            "last_modified": datetime.now().isoformat()
        }
    except Exception as e:
        print(f"❌ Error in update_instructions: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e)
        }


@app.get("/api/instructions/backups")
async def list_backups():
    """List all instruction backups"""
    try:
        data_dir = 'data'
        backups = []
        
        if os.path.exists(data_dir):
            for filename in os.listdir(data_dir):
                if filename.startswith('style_guide_backup_') and filename.endswith('.txt'):
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
            "backups": backups,
            "total": len(backups)
        }
    except Exception as e:
        print(f"❌ Error in list_backups: {e}")
        return {
            "success": False,
            "error": str(e)
        }


@app.post("/api/instructions/restore")
async def restore_backup(request: dict):
    """Restore instructions from a backup"""
    try:
        backup_filename = request.get("filename", "")
        
        if not backup_filename:
            return {
                "success": False,
                "error": "Backup filename is required"
            }
        
        backup_path = os.path.join('data', backup_filename)
        
        if not os.path.exists(backup_path):
            return {
                "success": False,
                "error": "Backup file not found"
            }
        
        # Read backup content
        with open(backup_path, 'r', encoding='utf-8') as f:
            backup_content = f.read()
        
        # Create a backup of current before restoring
        instructions_path = 'data/style_guide.txt'
        if os.path.exists(instructions_path):
            current_backup_path = f'data/style_guide_backup_before_restore_{datetime.now().strftime("%Y%m%d_%H%M%S")}.txt'
            with open(instructions_path, 'r', encoding='utf-8') as f:
                current_content = f.read()
            with open(current_backup_path, 'w', encoding='utf-8') as f:
                f.write(current_content)
            print(f"✅ Current version backed up: {current_backup_path}")
        
        # Restore from backup
        with open(instructions_path, 'w', encoding='utf-8') as f:
            f.write(backup_content)
        
        # Reload config
        config.BOT_STYLE_GUIDE = backup_content.strip()
        print(f"✅ Instructions restored from backup: {backup_filename}")
        
        return {
            "success": True,
            "message": f"Instructions restored from {backup_filename}",
            "last_modified": datetime.now().isoformat()
        }
    except Exception as e:
        print(f"❌ Error in restore_backup: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e)
        }


@app.get("/api/instructions/stats")
async def get_instructions_stats():
    """Get statistics about current instructions"""
    try:
        instructions_path = 'data/style_guide.txt'
        
        if not os.path.exists(instructions_path):
            return {
                "success": False,
                "error": "Instructions file not found"
            }
        
        with open(instructions_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Calculate stats
        lines = content.split('\n')
        words = content.split()
        characters = len(content)
        
        # Count sections (lines starting with specific markers)
        sections = len([line for line in lines if line.strip().startswith('✅') or line.strip().startswith('Section')])
        
        return {
            "success": True,
            "stats": {
                "lines": len(lines),
                "words": len(words),
                "characters": characters,
                "sections": sections,
                "last_modified": datetime.fromtimestamp(os.path.getmtime(instructions_path)).isoformat(),
                "file_size": os.path.getsize(instructions_path)
            }
        }
    except Exception as e:
        print(f"❌ Error in get_instructions_stats: {e}")
        return {
            "success": False,
            "error": str(e)
        }
