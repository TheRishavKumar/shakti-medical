import threading
import time
import os
import sys

# CRITICAL — set working directory to exe location
if getattr(sys, 'frozen', False):
    os.chdir(os.path.dirname(sys.executable))

from app import create_app

app = create_app()

def run_flask():
    app.run(debug=False, port=5000)

def run_backup_scheduler():
    try:
        import schedule
        from backup import backup_database

        # Auto backup every day at 10 PM
        schedule.every().day.at("22:00").do(backup_database)

        # Also backup when app starts (safety)
        backup_database()

        while True:
            schedule.run_pending()
            time.sleep(60)
    except Exception as e:
        print(f"Backup scheduler error: {e}")

if __name__ == "__main__":
    import webview

    # Start Flask server
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()

    # Start backup scheduler
    backup_thread = threading.Thread(target=run_backup_scheduler)
    backup_thread.daemon = True
    backup_thread.start()

    # Wait for Flask to start
    time.sleep(2)

    # Open desktop window — all links stay inside app
    webview.create_window(
        title="Shakti Medical Hall",
        url="http://127.0.0.1:5000",
        width=1280,
        height=800,
        resizable=True,
        min_size=(900, 600)
    )

    webview.start(icon="icon.ico")