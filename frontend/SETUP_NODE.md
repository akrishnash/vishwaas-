# Frontend setup when npm is not installed

If your system doesn't have Node/npm (or you can't install `nodejs-npm` due to permissions), use **nvm** to install Node in your user directory—no root required.

## 1. Install nvm (Node Version Manager)

Run in your terminal:

```bash
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash
```

Then reload your shell (or open a new terminal):

```bash
source ~/.bashrc
# or: source ~/.nvm/nvm.sh
```

Verify:

```bash
nvm --version
```

## 2. Install Node.js (includes npm)

```bash
nvm install 22
nvm use 22
node -v
npm -v
```

## 3. Run the frontend

From the **frontend** directory:

```bash
cd ~/codex/vishwaas/frontend
npm install
npm run dev
```

Then open http://localhost:3000 in your browser.

---

**Alternative (one-off download):** If you can't use nvm, download the Node.js Linux binary from https://nodejs.org/ (LTS), extract it, and add the `bin` directory to your `PATH`. Then run `npm install` and `npm run dev` from the frontend folder.
