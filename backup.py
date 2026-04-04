import os
import sys
import shutil
from datetime import datetime


def get_base_dir():
    """Get the directory where exe is running from."""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.abspath(os.path.join(os.path.dirname(__file__)))


def backup_database():
    """
    Creates a timestamped backup of the database.
    Keeps last 7 backups automatically.
    Returns the backup file path.
    """
    try:
        base_dir = get_base_dir()
        db_path = os.path.join(base_dir, 'instance', 'database.db')
        backup_dir = os.path.join(base_dir, 'backups')

        # Check if database exists
        if not os.path.exists(db_path):
            print("Database not found — skipping backup")
            return None

        # Create backups folder if not exists
        os.makedirs(backup_dir, exist_ok=True)

        # Create backup filename with date and time
        timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        backup_name = f'backup_{timestamp}.db'
        backup_path = os.path.join(backup_dir, backup_name)

        # Copy database to backup folder
        shutil.copy2(db_path, backup_path)
        print(f"Backup created: {backup_name}")

        # Keep only last 7 backups — delete older ones
        backups = sorted([
            f for f in os.listdir(backup_dir)
            if f.startswith('backup_') and f.endswith('.db')
        ])

        while len(backups) > 7:
            old_backup = os.path.join(backup_dir, backups[0])
            os.remove(old_backup)
            print(f"Old backup deleted: {backups[0]}")
            backups.pop(0)

        return backup_path

    except Exception as e:
        print(f"Backup error: {e}")
        return None


def get_backup_list():
    """Returns list of all available backups."""
    try:
        base_dir = get_base_dir()
        backup_dir = os.path.join(base_dir, 'backups')

        if not os.path.exists(backup_dir):
            return []

        backups = sorted([
            f for f in os.listdir(backup_dir)
            if f.startswith('backup_') and f.endswith('.db')
        ], reverse=True)

        return backups
    except:
        return []


def get_backup_dir():
    """Returns the backup directory path."""
    base_dir = get_base_dir()
    return os.path.join(base_dir, 'backups')