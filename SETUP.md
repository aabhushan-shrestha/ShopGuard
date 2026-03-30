# ShopGuard Setup

## Prerequisites

- **Python 3.10–3.13** (recommended). Python 3.14 is not yet fully supported by pip and many packages.
- A webcam connected to your system.

## Installation

1. **Create a virtual environment (recommended):**

   ```bash
   python -m venv venv
   # Windows
   venv\Scripts\activate
   # macOS/Linux
   source venv/bin/activate
   ```

2. **Install dependencies:**

   ```bash
   pip install -r requirements.txt
   ```

3. **Run the application:**

   ```bash
   python capture.py
   ```

   Press `q` to quit.

## Troubleshooting

### pip crashes on Python 3.14

Python 3.14 is very new and pip's bundled `distlib` may not support it yet. Options:

1. **Upgrade pip first:**

   ```bash
   python -m ensurepip --upgrade
   python -m pip install --upgrade pip
   ```

2. **Use the get-pip bootstrap:**

   ```bash
   # Windows (PowerShell)
   Invoke-WebRequest -Uri https://bootstrap.pypa.io/get-pip.py -OutFile get-pip.py
   python get-pip.py

   # macOS/Linux
   curl -sS https://bootstrap.pypa.io/get-pip.py | python
   ```

3. **Use Python 3.12 or 3.13 instead** — this is the most reliable option until package ecosystem support catches up.
