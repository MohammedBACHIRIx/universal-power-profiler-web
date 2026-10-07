# Deployment Guide: Heroku & Cloud Hosting

This repository is pre-configured for **1-click cloud deployment** on Heroku (as well as Render, Railway, or Fly.io).

---

## ⚡ Option 1: Automatic GitHub Integration (Recommended)

1. Open your [Heroku Dashboard](https://dashboard.heroku.com/).
2. Click **New** ➔ **Create new app**.
3. Choose an app name (e.g. `universal-power-profiler`) and region.
4. Under the **Deploy** tab:
   - Select **GitHub** as the deployment method.
   - Search for repository `universal-power-profiler-web` and click **Connect**.
   - Under *Manual deploy*, select branch `main` and click **Deploy Branch**.
5. Once deployed, click **Open app**! Your Web IDE is live with SSL (`https://...` and `wss://...`).

---

## 💻 Option 2: Deploy Using Heroku CLI

If you have the Heroku CLI installed on your machine:

```bash
# 1. Log in to Heroku
heroku login

# 2. Create the Heroku app
heroku create universal-power-profiler

# 3. Deploy code
git push heroku main

# 4. Open the deployed application in your browser
heroku open
```

---

## 🔌 Using Physical Serial Meters from a Cloud Host

When running on a cloud server (like Heroku), note how physical hardware communicates:
1. **Direct Web Serial API (Chrome / Edge)**:
   - Click the top-bar button **"Browser Web Serial API"**.
   - Your browser talks directly to your USB/RS-232 COM port on your local machine, while loading the UI from Heroku.
2. **Ethernet TCP (WIZnet WIZ750SR-110)**:
   - Specify the public IP or VPN/port-forwarded IP and port of the WIZ750SR gateway (e.g. `your-lab-ip:5000`).
3. **Built-in Virtual Simulators**:
   - `SIMULATOR-P1` and `SIMULATOR-P2` run directly on Heroku for cloud testing, student demos, and validation.
