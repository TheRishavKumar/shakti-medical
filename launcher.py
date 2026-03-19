import threading
import time
import webview
from app import create_app

app = create_app()

def run_flask():
    app.run(debug=False, port=5000)

if __name__ == "__main__":
    t = threading.Thread(target=run_flask)
    t.daemon = True
    t.start()

    time.sleep(2)

    webview.create_window(
        title="Shakti Medical Hall",
        url="http://127.0.0.1:5000",
        width=1200,
        height=750,
        resizable=True,
        min_size=(800, 600)
    )
    webview.start(icon="icon.ico")